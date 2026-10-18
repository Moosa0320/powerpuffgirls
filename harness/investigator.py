"""Tool-calling investigator loop (guide 7.5) with verifier retry and safe fallback (7.6).

The field and window are fixed by the harness; the model can only read this field's records.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend.models import Event, EventType, Photo
from harness import engine
from harness.jsonutil import parse_json_object
from harness.llm.base import LLMProvider, ToolCall
from harness.skill_loader import SkillLoader, SkillMeta
from harness.verifier import (
    DISCLAIMER, Evidence, EventFact, VerificationResult, load_banned_patterns,
    safe_template_report, verify_report,
)

MAX_STEPS = 8
MAX_VERIFY_RETRIES = 2
SKILL_NAME = "farm-record-investigation"
LANG_NAMES = {"en": "English", "ur": "Urdu (Urdu script)", "roman": "Roman Urdu"}

REPORT_SHAPE = (
    '{"sections": {"records_show": [...], "worth_investigating": [...], "questions_next": [...], '
    '"missing_records": [...], "photo_observations": [...]}, "disclaimer": "..."}\n'
    'Each claim: {"text": "...", "type": "fact" | "possibility" | "question", '
    '"event_ids": ["E-001"], "photo_ids": ["P-001"], "unconfirmed": true}'
)


def _tool(name: str, description: str, props: dict[str, Any] | None = None,
          required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOL_SPECS = [
    _tool("get_timeline", "Chronological events and photos for this field in the investigation window."),
    _tool("find_gaps", "Missing irrigation, fertilizer or weather records and incomplete events."),
    _tool("compare_values", "Change versus the previous record of the same type and product.",
          {"type": {"type": "string", "enum": [t.value for t in EventType]}}, ["type"]),
    _tool("get_photos", "Photos for this field with vision observations and verification status."),
    _tool("read_reference", "Read a reference file from the skill, e.g. banned-claims.md.",
          {"name": {"type": "string"}}, ["name"]),
]


def harness_rules(lang: str) -> str:
    return (
        "You are running inside the FasalNama harness.\n"
        "- Use the tools to read records. Never invent events, IDs, dates or numbers.\n"
        "- When finished, reply with ONLY a JSON object of this shape:\n" + REPORT_SHAPE + "\n"
        "- Every fact cites at least one event ID (E-###) or photo ID (P-###).\n"
        "- Photo claims set \"unconfirmed\": true unless the farmer verified the photo.\n"
        "- missing_records must list every gap returned by find_gaps.\n"
        "- Never name a disease or a cause as fact. Never recommend a pesticide, fungicide or dosage.\n"
        f"- Write claim text in {LANG_NAMES.get(lang, 'English')}.\n"
        f'- "disclaimer" must be exactly: "{DISCLAIMER}"\n'
    )


def build_evidence(session: Session, field_id: int, symptom_date: date, gaps_found: bool) -> Evidence:
    events = {
        e.display_id: EventFact(e.display_id, e.occurred_at, e.type.value, e.product, e.quantity, e.unit)
        for e in session.execute(select(Event).where(Event.field_id == field_id)).scalars()
    }
    photos = {p.display_id: p.verified_by_farmer
              for p in session.execute(select(Photo).where(Photo.field_id == field_id)).scalars()}
    return Evidence(events=events, photos=photos, gaps_found=gaps_found, symptom_date=symptom_date)


@dataclass
class InvestigationOutcome:
    report: dict[str, Any]
    used_fallback: bool
    verifier_log: list[dict[str, Any]] = field(default_factory=list)
    model_info: dict[str, Any] = field(default_factory=dict)
    steps: int = 0


class ToolBox:
    def __init__(self, session: Session, field_id: int, start: date, end: date, window_days: int,
                 loader: SkillLoader, meta: SkillMeta) -> None:
        self.session, self.field_id = session, field_id
        self.start, self.end, self.window_days = start, end, window_days
        self.loader, self.meta = loader, meta

    def dispatch(self, call: ToolCall) -> str:
        try:
            return json.dumps(self._run(call.name, call.arguments or {}), default=str, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - tool errors go back to the model, typed
            return json.dumps({"error": type(exc).__name__, "detail": str(exc)[:200]})

    def _run(self, name: str, args: dict[str, Any]) -> Any:
        if name == "get_timeline":
            return [asdict(i) for i in engine.get_timeline(self.session, self.field_id, self.start, self.end)]
        if name == "find_gaps":
            gaps = engine.find_gaps(self.session, self.field_id, self.window_days, end=self.end)
            return {**asdict(gaps), "has_gaps": gaps.has_gaps, "window_days": self.window_days}
        if name == "compare_values":
            return [asdict(c) for c in engine.compare_values(self.session, self.field_id, EventType(args["type"]))]
        if name == "get_photos":
            rows = self.session.execute(select(Photo).where(Photo.field_id == self.field_id)).scalars()
            return [{"photo_id": p.display_id, "taken_at": p.taken_at, "quality_flags": p.quality_flags,
                     "vision_observation": p.vision_observation, "verified_by_farmer": p.verified_by_farmer}
                    for p in rows]
        if name == "read_reference":
            return {"name": args["name"], "content": self.loader.read_reference(self.meta, args["name"])}
        return {"error": f"unknown tool {name}"}


class Investigator:
    def __init__(self, session: Session, llm: LLMProvider | None, loader: SkillLoader | None = None) -> None:
        self.session, self.llm = session, llm
        self.loader = loader or SkillLoader()
        self.banned = load_banned_patterns()

    def run(self, field_id: int, symptom_date: date, window_days: int = 14,
            lang: str = "en") -> InvestigationOutcome:
        start, end = symptom_date - timedelta(days=window_days), symptom_date
        timeline = engine.get_timeline(self.session, field_id, start, end)
        gaps = engine.find_gaps(self.session, field_id, window_days, end=end)
        evidence = build_evidence(self.session, field_id, symptom_date, gaps.has_gaps)
        log: list[dict[str, Any]] = []
        info: dict[str, Any] = {"llm": self.llm.name if self.llm else None, "skill": SKILL_NAME}

        def fallback(reason: str, steps: int) -> InvestigationOutcome:
            log.append({"event": "fallback", "reason": reason})
            report = safe_template_report(timeline, gaps, window_days)
            report["used_fallback"] = True
            info["disclosure"] = list(self.loader.log.levels)
            return InvestigationOutcome(report, True, log, info, steps)

        meta = self.loader.skills.get(SKILL_NAME)
        if self.llm is None:
            return fallback("no LLM backend available", 0)
        if meta is None:
            return fallback("skill not found", 0)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.loader.load_body(meta) + "\n\n" + harness_rules(lang)},
            {"role": "user", "content": f"The symptom was first seen on {symptom_date.isoformat()}. "
                                        f"Investigate the {window_days} days before it."},
        ]
        tools = ToolBox(self.session, field_id, start, end, window_days, self.loader, meta)
        retries = 0
        for step in range(1, MAX_STEPS + 1):
            res = self.llm.chat(messages, tools=TOOL_SPECS)
            if not res.ok or res.value is None:
                log.append({"step": step, "event": "llm_error", "error": asdict(res.error) if res.error else None})
                return fallback("LLM call failed", step)
            reply = res.value
            if reply.tool_calls:
                messages.append(reply.raw_message or {"role": "assistant", "content": reply.content})
                for call in reply.tool_calls:
                    log.append({"step": step, "event": "tool", "name": call.name})
                    messages.append(self.llm.tool_result_message(call, tools.dispatch(call)))
                continue
            report = parse_json_object(reply.content)
            result = (verify_report(report, evidence, self.banned) if report is not None
                      else VerificationResult(False, ["final answer is not a JSON object"]))
            log.append({"step": step, "event": "verify", "ok": result.ok, "errors": result.errors})
            if result.ok and report is not None:
                report["used_fallback"] = False
                info["disclosure"] = list(self.loader.log.levels)
                return InvestigationOutcome(report, False, log, info, step)
            if retries >= MAX_VERIFY_RETRIES:
                return fallback("verifier rejected the report after retries", step)
            retries += 1
            messages.append({"role": "assistant", "content": reply.content})
            messages.append({"role": "user", "content": "The verifier rejected your report. Fix every "
                             "error and return only the corrected JSON report:\n- " + "\n- ".join(result.errors)})
        return fallback("step cap reached", MAX_STEPS)