"""Tests for the investigator loop (guide 7.5 and 7.6, requirements 9.1-9.5 and 10.7).

FakeLLM plays the model with scripted tool calls, final reports and errors. The records are
seeded in the test database. No network calls.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.backend.db.service import create_event, next_photo_display_id
from app.backend.models import EventSource, EventType, Farm, Field, Photo
from harness.investigator import (
    MAX_STEPS,
    MAX_VERIFY_RETRIES,
    SKILL_NAME,
    InvestigationOutcome,
    Investigator,
    harness_rules,
)
from harness.llm.base import LLMReply, ToolCall
from harness.providers.fakes import FakeLLM
from harness.skill_loader import SkillLoader
from harness.verifier import DISCLAIMER, SECTIONS

TODAY = date(2026, 3, 15)
SYMPTOM = date(2026, 3, 12)  # the 14-day window runs from 2026-02-26 to 2026-03-12
L1 = "L1:frontmatter"
L2 = f"L2:body:{SKILL_NAME}"
L3_BANNED = "L3:reference:banned-claims.md"
TOOL_NAMES = ["get_timeline", "find_gaps", "compare_values", "get_photos", "read_reference"]
WINDOW_EVENTS = ["E-002", "E-003", "E-004", "E-005"]  # E-001 is older than the window

# A report the verifier accepts for the seeded field: facts cite their events, numbers and dates
# match the records, the null-quantity gap (E-005) is listed and the photo claim is unconfirmed.
GOOD_REPORT: dict[str, Any] = {
    "sections": {
        "records_show": [
            {"text": "The records show 2 bori urea on 2026-03-05 (E-002).", "type": "fact",
             "event_ids": ["E-002"], "photo_ids": []},
        ],
        "worth_investigating": [
            {"text": "The urea increase from 1 bori to 2 bori (E-001, E-002) may be worth "
                     "investigating.", "type": "possibility", "event_ids": ["E-001", "E-002"],
             "photo_ids": []},
        ],
        "questions_next": [
            {"text": "Has the symptom spread to other plants or fields since it was first seen?",
             "type": "question", "event_ids": [], "photo_ids": []},
        ],
        "missing_records": [
            {"text": "Spray quantity was not recorded (E-005).", "type": "fact",
             "event_ids": ["E-005"], "photo_ids": []},
        ],
        "photo_observations": [
            {"text": "Photo P-001 may show yellow spots on the leaves (unconfirmed).",
             "type": "possibility", "event_ids": [], "photo_ids": ["P-001"], "unconfirmed": True},
        ],
    },
    "disclaimer": DISCLAIMER,
}


def _report_with(section: str, claim: dict[str, Any]) -> str:
    """GOOD_REPORT as model text, with one more claim in a section."""
    report = copy.deepcopy(GOOD_REPORT)
    report["sections"][section].append(claim)
    return json.dumps(report)


GOOD = json.dumps(GOOD_REPORT)
FAKE_ID = _report_with("records_show", {"text": "The records show an irrigation (E-999).",
                                        "type": "fact", "event_ids": ["E-999"], "photo_ids": []})
FAKE_ID_ERROR = "records_show[1]: cited event E-999 does not exist for this field"
DIAGNOSIS = _report_with("worth_investigating", {"text": "This is a fungal infection.",
                                                 "type": "possibility", "event_ids": [],
                                                 "photo_ids": []})
NOT_JSON = "The records look fine to me."


@pytest.fixture()
def field_id(session: Session) -> int:
    """A field with the sample farm's signals: urea doubled (E-001 to E-002), rain (E-003),
    irrigation (E-004), a spray with no quantity (E-005, a gap) and an unverified photo P-001."""
    farm = Farm(name="Test farm")
    field = Field(farm=farm, name="North", crop="tomato")
    session.add_all([farm, field])
    session.flush()
    for occurred_at, event_type, details in (
        (date(2026, 2, 20), EventType.fertilizer,
         {"product": "urea", "quantity": 1.0, "unit": "bori"}),
        (date(2026, 3, 5), EventType.fertilizer,
         {"product": "urea", "quantity": 2.0, "unit": "bori"}),
        (date(2026, 3, 6), EventType.weather,
         {"product": "rainfall", "quantity": 45.0, "unit": "mm"}),
        (date(2026, 3, 8), EventType.irrigation, {"quantity": 1.0, "unit": "tanki"}),
        (date(2026, 3, 9), EventType.pesticide, {"product": "spray"}),
    ):
        create_event(session, field_id=field.id, type=event_type, occurred_at=occurred_at,
                     source=EventSource.farmer_text, today=TODAY, **details)
    session.add(Photo(field_id=field.id, display_id=next_photo_display_id(session, field.id),
                      taken_at=datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
                      vision_observation={"description": "yellow spots on lower leaves"}))
    session.commit()
    return field.id


def _run(session: Session, field_id: int, replies: list[Any], loader: SkillLoader | None = None,
         lang: str = "en") -> tuple[InvestigationOutcome, FakeLLM]:
    llm = FakeLLM(replies)
    return Investigator(session, llm, loader).run(field_id, SYMPTOM, 14, lang), llm


def _tool_step(*calls: tuple[str, dict[str, Any]]) -> LLMReply:
    """One model turn that only calls tools."""
    return LLMReply(tool_calls=[ToolCall(name, args, id=f"call-{i}")
                                for i, (name, args) in enumerate(calls, 1)])


def _tool_results(call: dict[str, Any]) -> list[Any]:
    """The tool results at the end of the messages of one recorded LLM call, parsed."""
    results: list[Any] = []
    for message in reversed(call["messages"]):
        if message["role"] != "tool":
            break
        results.insert(0, json.loads(message["content"]))
    return results


def _entries(outcome: InvestigationOutcome, event: str) -> list[dict[str, Any]]:
    return [entry for entry in outcome.verifier_log if entry["event"] == event]


def _assert_fallback(outcome: InvestigationOutcome, reason: str, disclosure: list[str],
                     level: str) -> None:
    """The code-written safe report for the seeded window, with the reason logged last."""
    assert outcome.used_fallback is True and outcome.report["used_fallback"] is True
    assert outcome.report["disclaimer"] == DISCLAIMER
    sections = outcome.report["sections"]
    assert set(sections) == set(SECTIONS)
    records = [claim["event_ids"] for claim in sections["records_show"]]
    assert records == [[event_id] for event_id in WINDOW_EVENTS]
    assert [claim["event_ids"] for claim in sections["missing_records"]] == [["E-005"]]
    assert [(claim["photo_ids"], claim["unconfirmed"])
            for claim in sections["photo_observations"]] == [(["P-001"], True)]
    assert outcome.verifier_log[-1] == {"event": "fallback", "reason": reason}
    assert outcome.model_info["disclosure"] == disclosure
    assert outcome.model_info["disclosure_level"] == level


# --- prompt and tools (9.1, 9.2) -----------------------------------------------------------
def test_system_prompt_is_the_skill_body_plus_harness_rules(
    session: Session, field_id: int
) -> None:
    _, llm = _run(session, field_id, [GOOD], lang="ur")
    system, user = llm.calls[0]["messages"]
    assert system["role"] == "system" and user["role"] == "user"
    assert system["content"].startswith("# Farm Record Investigation")  # the SKILL.md body
    assert "## Procedure" in system["content"]
    assert system["content"].endswith(harness_rules("ur"))
    assert f'"disclaimer" must be exactly: "{DISCLAIMER}"' in system["content"]
    assert "Write claim text in Urdu (Urdu script)." in system["content"]
    assert "2026-03-12" in user["content"] and "14 days" in user["content"]


def test_all_five_tools_are_offered_on_every_call(session: Session, field_id: int) -> None:
    _, llm = _run(session, field_id, [_tool_step(("get_timeline", {})), GOOD])
    assert len(llm.calls) == 2
    for call in llm.calls:
        assert [spec["function"]["name"] for spec in call["tools"]] == TOOL_NAMES


# --- tool results each step (9.3) ----------------------------------------------------------
def test_tool_results_go_back_to_the_model_each_step(session: Session, field_id: int) -> None:
    outcome, llm = _run(session, field_id, [
        _tool_step(("get_timeline", {}), ("find_gaps", {})),
        _tool_step(("compare_values", {"type": "fertilizer"}), ("get_photos", {})),
        _tool_step(("compare_values", {"type": "rainfall"})),  # not an event type
        GOOD,
    ])
    timeline, gaps = _tool_results(llm.calls[1])
    assert [item["display_id"] for item in timeline] == [*WINDOW_EVENTS, "P-001"]
    assert gaps["null_quantity_events"] == ["E-005"] and gaps["has_gaps"] is True
    changes, photos = _tool_results(llm.calls[2])
    assert [(c["previous_event_id"], c["event_id"], c["percent_change"]) for c in changes] == [
        ("E-001", "E-002", 100.0)]
    assert [(p["photo_id"], p["verified_by_farmer"]) for p in photos] == [("P-001", False)]
    [error] = _tool_results(llm.calls[3])
    assert error["error"] == "ValueError"  # a typed error the model can read
    # The loop went on after the tool error, and the final report was verified.
    assert outcome.used_fallback is False and outcome.steps == 4
    assert [(entry["step"], entry["name"]) for entry in _entries(outcome, "tool")] == [
        (1, "get_timeline"), (1, "find_gaps"), (2, "compare_values"), (2, "get_photos"),
        (3, "compare_values")]


# --- the verified report (9.4, 9.5) --------------------------------------------------------
def test_verified_report_is_returned_with_all_five_sections(
    session: Session, field_id: int
) -> None:
    outcome, llm = _run(session, field_id, [_tool_step(("get_timeline", {})), GOOD])
    assert outcome.used_fallback is False and outcome.report["used_fallback"] is False
    assert set(outcome.report["sections"]) == set(SECTIONS)
    assert outcome.report["sections"] == GOOD_REPORT["sections"]
    assert outcome.report["disclaimer"] == DISCLAIMER
    assert outcome.steps == len(llm.calls) == 2
    assert outcome.verifier_log[-1] == {"step": 2, "event": "verify", "ok": True, "errors": []}


# --- verifier retry and safe fallback (10.7) -----------------------------------------------
def test_rejected_report_is_retried_with_the_errors(session: Session, field_id: int) -> None:
    outcome, llm = _run(session, field_id, [FAKE_ID, GOOD])
    assert outcome.used_fallback is False and outcome.steps == 2
    rejected, feedback = llm.calls[1]["messages"][-2:]
    assert rejected == {"role": "assistant", "content": FAKE_ID}
    assert feedback["role"] == "user"
    assert feedback["content"].startswith("The verifier rejected your report.")
    assert FAKE_ID_ERROR in feedback["content"]
    assert _entries(outcome, "verify") == [
        {"step": 1, "event": "verify", "ok": False, "errors": [FAKE_ID_ERROR]},
        {"step": 2, "event": "verify", "ok": True, "errors": []},
    ]


def test_persistent_rejection_falls_back_after_two_retries(
    session: Session, field_id: int
) -> None:
    outcome, llm = _run(session, field_id, [NOT_JSON, FAKE_ID, DIAGNOSIS, GOOD])
    assert len(llm.calls) == 1 + MAX_VERIFY_RETRIES
    assert llm.replies == [GOOD]  # no fourth report was asked for
    _assert_fallback(outcome, "verifier rejected the report after retries", [L1, L2], "L2")
    assert outcome.steps == 3
    verifies = _entries(outcome, "verify")
    assert [(entry["step"], entry["ok"]) for entry in verifies] == [(1, False), (2, False),
                                                                     (3, False)]
    assert verifies[0]["errors"] == ["final answer is not a JSON object"]
    assert verifies[1]["errors"] == [FAKE_ID_ERROR]
    [diagnosis_error] = verifies[2]["errors"]
    assert diagnosis_error.startswith("worth_investigating[1]: diagnosis or cause-as-fact wording")


def test_report_the_verifier_cannot_check_is_rejected_not_raised(
    session: Session, field_id: int
) -> None:
    # An ID sent as an object makes the verifier's lookups raise TypeError; this used to end the
    # run with the exception instead of a retry or the safe fallback.
    malformed = _report_with("records_show", {"text": "The records show urea.", "type": "fact",
                                              "event_ids": [{"id": "E-002"}], "photo_ids": []})
    outcome, llm = _run(session, field_id, [malformed, GOOD])
    assert outcome.used_fallback is False and outcome.steps == 2
    first, second = _entries(outcome, "verify")
    assert first["ok"] is False and len(first["errors"]) == 1
    assert first["errors"][0].startswith("report could not be checked (TypeError)")
    assert first["errors"][0] in llm.calls[1]["messages"][-1]["content"]  # sent back to the model
    assert second["ok"] is True


def test_no_llm_falls_back(session: Session, field_id: int) -> None:
    outcome = Investigator(session, None).run(field_id, SYMPTOM)
    _assert_fallback(outcome, "no LLM backend available", [L1], "L1")
    assert outcome.steps == 0 and outcome.model_info["llm"] is None


def test_missing_skill_falls_back_without_calling_the_model(
    session: Session, field_id: int, tmp_path: Path
) -> None:
    outcome, llm = _run(session, field_id, [GOOD], loader=SkillLoader(tmp_path))  # no skills
    _assert_fallback(outcome, "skill not found", [L1], "L1")
    assert llm.calls == [] and outcome.steps == 0


def test_llm_error_falls_back_with_a_typed_error(session: Session, field_id: int) -> None:
    raw = "connection reset while reading /srv/fasalnama/audio/farmer-17.webm"
    outcome, _ = _run(session, field_id, [RuntimeError(raw)])
    _assert_fallback(outcome, "LLM call failed", [L1, L2], "L2")
    assert outcome.steps == 1
    assert outcome.verifier_log[0] == {"step": 1, "event": "llm_error", "error": {
        "provider": "llm.fake", "kind": "unavailable", "message": "RuntimeError"}}
    assert "farmer-17.webm" not in json.dumps(outcome.verifier_log)  # no raw message


# --- step cap (9.3) ------------------------------------------------------------------------
def test_step_cap_stops_endless_tool_calls(session: Session, field_id: int) -> None:
    replies = [_tool_step(("get_timeline", {})) for _ in range(MAX_STEPS + 3)]
    outcome, llm = _run(session, field_id, replies)
    assert len(llm.calls) == MAX_STEPS and len(llm.replies) == 3
    _assert_fallback(outcome, "step cap reached", [L1, L2], "L2")
    assert outcome.steps == MAX_STEPS
    assert [entry["step"] for entry in _entries(outcome, "tool")] == list(range(1, MAX_STEPS + 1))
    assert _entries(outcome, "verify") == []


def test_step_cap_is_within_the_guides_range() -> None:
    assert 6 <= MAX_STEPS <= 8
    assert MAX_VERIFY_RETRIES == 2


# --- model_info and the per-run disclosure log (8.5) ---------------------------------------
def test_model_info_records_the_model_the_skill_and_disclosure(
    session: Session, field_id: int
) -> None:
    read = _tool_step(("read_reference", {"name": "banned-claims"}))
    outcome, _ = _run(session, field_id, [read, GOOD])
    assert outcome.used_fallback is False
    assert outcome.model_info == {"llm": "llm.fake", "skill": SKILL_NAME,
                                  "disclosure": [L1, L2, L3_BANNED], "disclosure_level": "L3"}


def test_each_run_has_its_own_disclosure_log(session: Session, field_id: int) -> None:
    loader = SkillLoader()
    llm = FakeLLM([_tool_step(("read_reference", {"name": "banned-claims"})), GOOD, GOOD])
    investigator = Investigator(session, llm, loader)  # one loader for both runs
    first = investigator.run(field_id, SYMPTOM)
    second = investigator.run(field_id, SYMPTOM)
    assert second.model_info["disclosure"] == [L1, L2]  # none of the first run's L3 entries
    assert second.model_info["disclosure_level"] == "L2"
    assert first.model_info["disclosure"] == [L1, L2, L3_BANNED]  # the first run's record is kept
    assert first.model_info["disclosure_level"] == "L3"
    assert loader.log.levels == [L1, L2]
