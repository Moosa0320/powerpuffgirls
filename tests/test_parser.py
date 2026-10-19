"""Parser unit tests (guide task 5, requirement 5.1-5.6).

The LLM is always a FakeLLM with scripted replies: no model and no network. The model may
only return days_ago; code resolves the date, normalizes units and products, marks each
event's date certainty and returns proposals that are never saved.
"""
from __future__ import annotations

import ast
import csv
import inspect
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.backend.db.service import create_event
from app.backend.models import DateCertainty, EventSource, EventType, Farm, Field
from harness import parser
from harness.engine import compare_values
from harness.providers.base import ProviderResponseError
from harness.providers.fakes import FakeLLM

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = ROOT / "skill" / "farm-record-investigation" / "examples" / "sample_farm.csv"
TODAY = date(2026, 3, 15)
URDU_SCRIPT = re.compile(r"[\u0600-\u06FF]")
CANONICAL_UNITS = {"bori", "kg", "litre", "ml", "tanki", "acre", "kanal", "mm"}
CANONICAL_PRODUCTS = {"urea", "DAP", "spray", "rainfall", "wheat", "tomato"}
MODEL_FIELDS = {"type", "product", "quantity", "unit", "days_ago", "symptom", "confidence"}


def ev(type_: str = "fertilizer", days_ago: int | None = 0, **fields: Any) -> dict[str, Any]:
    """One event as the model returns it."""
    return {"type": type_, "product": None, "quantity": None, "unit": None,
            "days_ago": days_ago, "symptom": None, "confidence": 0.9, **fields}


def reply(*events: dict[str, Any]) -> str:
    return json.dumps({"events": list(events)}, ensure_ascii=False)


def parse(text: str, *replies: Any, today: date = TODAY,
          field_names: list[str] | None = None) -> tuple[parser.ParseResult, FakeLLM]:
    llm = FakeLLM(replies=list(replies))
    return parser.parse_text(text, today, llm, field_names=field_names), llm


# --- days_ago -> calendar date, computed by code ------------------------------------------

@pytest.mark.parametrize(
    ("note", "days_ago", "today", "expected"),
    [
        ("aaj pani diya", 0, TODAY, date(2026, 3, 15)),
        ("kal pani diya", 1, TODAY, date(2026, 3, 14)),
        ("parson pani diya", 2, TODAY, date(2026, 3, 13)),
        ("7 din pehle pani diya", 7, TODAY, date(2026, 3, 8)),
        ("3 din pehle pani diya", 3, date(2026, 3, 2), date(2026, 2, 27)),
        ("5 din pehle pani diya", 5, date(2026, 1, 2), date(2025, 12, 28)),
        ("kal pani diya", 1, date(2024, 3, 1), date(2024, 2, 29)),
    ],
    ids=["today", "yesterday", "parson", "7-days", "month-boundary", "year-boundary", "leap-day"],
)
def test_days_ago_is_resolved_to_a_calendar_date(
    note: str, days_ago: int, today: date, expected: date
) -> None:
    result, _ = parse(note, reply(ev("irrigation", days_ago)), today=today)
    assert result.error is None
    [event] = result.events
    assert event.occurred_at == expected
    assert event.date_certainty == "exact"


def test_days_ago_resolution_holds_across_the_allowed_range() -> None:
    rng = random.Random(51)
    for _ in range(200):
        today = date(2020, 1, 1) + timedelta(days=rng.randrange(4000))
        days_ago = rng.randint(0, 365)
        result, _ = parse("pani diya", reply(ev("irrigation", days_ago)), today=today)
        [event] = result.events
        assert event.occurred_at == today - timedelta(days=days_ago), (today, days_ago)


def test_an_unknown_date_stays_unknown_and_nothing_is_invented() -> None:
    result, _ = parse("pani diya tha kab yaad nahi", reply(ev("irrigation", None)))
    [event] = result.events
    assert event.occurred_at is None
    assert event.date_certainty == "unknown"
    assert (event.product, event.quantity, event.unit) == (None, None, None)


def test_an_unknown_date_is_not_made_approximate_by_a_vague_clause() -> None:
    note = "pichle hafte urea dali, pani kab diya yaad nahi"
    result, _ = parse(note, reply(ev("fertilizer", 7, product="urea"), ev("irrigation", None)))
    assert [(e.occurred_at, e.date_certainty) for e in result.events] == [
        (date(2026, 3, 8), "approximate"), (None, "unknown")]


# --- date certainty per event, not per note -----------------------------------------------

@pytest.mark.parametrize(
    ("note", "days", "expected"),
    [
        ("pichle hafte DAP dali, aaj pani diya", [7, 0], ["approximate", "exact"]),
        ("pichle hafte DAP dali aur aaj pani diya", [7, 0], ["approximate", "exact"]),
        ("kal 1 tanki pani diya lekin urea takreeban 10 din pehle dali thi", [1, 10],
         ["exact", "approximate"]),
        ("parson spray kiya magar DAP pichle mahine dali", [2, 30], ["exact", "approximate"]),
        ("Watered today and applied urea about a week ago", [0, 7], ["exact", "approximate"]),
        ("Day before yesterday I sprayed. Urea went in around a month ago", [2, 30],
         ["exact", "approximate"]),
        ("پچھلے ہفتے ڈی اے پی ڈالی اور آج پانی دیا", [7, 0], ["approximate", "exact"]),
        ("تقریباً ایک مہینہ پہلے گندم بوئی۔ کل سپرے کیا", [30, 1], ["approximate", "exact"]),
        ("۳ دن پہلے سپرے کیا، پچھلے ہفتے یوریا ڈالی", [3, 7], ["exact", "approximate"]),
        ("aaj pani diya aur kal urea dali", [0, 1], ["exact", "exact"]),
    ],
)
def test_date_certainty_is_marked_per_event(note: str, days: list[int], expected: list[str]) -> None:
    result, _ = parse(note, reply(*(ev("fertilizer", d) for d in days)))
    assert [e.date_certainty for e in result.events] == expected


EXACT_CLAUSES = [
    ("aaj 2 bori urea dali", 0), ("kal pani diya", 1), ("parson spray kiya", 2),
    ("3 din pehle DAP dali", 3), ("آج پانی دیا", 0), ("کل یوریا ڈالی", 1),
    ("پرسوں سپرے کیا", 2), ("۴ دن پہلے پانی دیا", 4), ("watered yesterday", 1),
    ("sprayed today", 0), ("5 days ago applied DAP", 5), ("day before yesterday gave water", 2),
]
VAGUE_CLAUSES = [
    ("pichle hafte DAP dali", 7), ("takreeban 10 din pehle spray kiya", 10),
    ("pichle mahine urea dali", 30), ("پچھلے ہفتے سپرے کیا", 7),
    ("تقریبا ایک مہینہ پہلے گندم بوئی", 30), ("about two weeks ago sprayed", 14),
]
JOINERS = [", ", ". ", "; ", "\n", "۔ ", "، ", " aur ", " phir ", " lekin ", " magar ", " and ",
           " then ", " but ", " اور ", " پھر ", " لیکن ", " مگر "]


def test_each_event_keeps_its_own_certainty_in_random_notes() -> None:
    rng = random.Random(7)
    for _ in range(300):
        clauses = rng.sample(EXACT_CLAUSES + VAGUE_CLAUSES, rng.randint(1, 4))
        note = clauses[0][0]
        for text, _ in clauses[1:]:
            note += rng.choice(JOINERS) + text
        expected = ["approximate" if c in VAGUE_CLAUSES else "exact" for c in clauses]
        result, _ = parse(note, reply(*(ev("fertilizer", d) for _, d in clauses)))
        assert [e.date_certainty for e in result.events] == expected, note


@pytest.mark.parametrize(
    ("note", "days_ago"),
    [
        ("ek mahina pehle gandum boi", 30),
        ("do hafton pehle DAP dali", 14),
        ("takriban 10 din pehle spray kiya", 10),
        ("ایک ہفتہ پہلے سپرے کیا", 7),
        ("دو مہینے پہلے ڈی اے پی ڈالی", 60),
        ("تقریبا دس دن پہلے یوریا ڈالی", 10),
        ("تقریباً دس دن پہلے یوریا ڈالی", 10),
        ("کچھ دن پہلے پانی دیا", 4),
        ("لگ بھگ دس دن پہلے سپرے کیا", 10),
    ],
)
def test_vague_date_spellings_are_recognized(note: str, days_ago: int) -> None:
    result, _ = parse(note, reply(ev("fertilizer", days_ago)))
    assert result.events[0].date_certainty == "approximate"


def test_a_hedge_about_an_amount_makes_its_clause_approximate() -> None:
    # Documented limitation: "about 40 mm" hedges the amount, yet the whole clause counts as vague.
    note = "aaj pani diya, kal about 40 mm barish hui"
    result, _ = parse(note, reply(ev("irrigation", 0),
                                  ev("weather", 1, product="rainfall", quantity=40, unit="mm")))
    assert [e.date_certainty for e in result.events] == ["exact", "approximate"]


def test_date_certainty_for_one_event() -> None:
    note = "pichle hafte DAP dali, aaj pani diya"
    assert parser.date_certainty(0, note) == "exact"
    assert parser.date_certainty(7, note) == "approximate"
    assert parser.date_certainty(None, note) == "unknown"
    assert parser.date_certainty(5, "urea dali") == "exact"  # no vague clause in the note


@pytest.mark.parametrize(
    ("note", "clauses"),
    [
        ("pichle hafte DAP dali, aaj pani diya", ["pichle hafte DAP dali", "aaj pani diya"]),
        ("urea dali aur pani diya phir spray kiya lekin patta peela hai magar kam",
         ["urea dali", "pani diya", "spray kiya", "patta peela hai", "kam"]),
        ("Watered today and sprayed. Rain came!", ["Watered today", "sprayed", "Rain came"]),
        ("Watered today then sprayed but rain came", ["Watered today", "sprayed", "rain came"]),
        ("پچھلے ہفتے یوریا ڈالی اور آج پانی دیا۔ کل سپرے کیا، پھر بارش ہوئی",
         ["پچھلے ہفتے یوریا ڈالی", "آج پانی دیا", "کل سپرے کیا", "بارش ہوئی"]),
        ("لیکن پانی کم تھا مگر دیا", ["پانی کم تھا", "دیا"]),
        ("2.5 bori urea aur 1,5 litre", ["2.5 bori urea", "1,5 litre"]),
        ("pichle hafte D.A.P dali. aaj pani diya", ["pichle hafte D.A.P dali", "aaj pani diya"]),
        ("khet ke andar pani diya", ["khet ke andar pani diya"]),
    ],
)
def test_split_clauses(note: str, clauses: list[str]) -> None:
    assert parser.split_clauses(note) == clauses


@pytest.mark.parametrize(
    ("clause", "days"),
    [
        ("aaj pani diya", {0}), ("Today I watered", {0}), ("آج پانی دیا", {0}),
        ("kal urea dali", {1}), ("watered yesterday", {1}), ("کل یوریا ڈالی", {1}),
        ("parson spray kiya", {2}), ("the day before yesterday", {2}), ("پرسوں سپرے کیا", {2}),
        ("3 din pehle DAP dali", {3}), ("10 days ago", {10}), ("۳ دن پہلے", {3}),
        ("aaj pani aur kal urea", {0, 1}),
        ("2 کلو یوریا ڈالی", set()), ("pattay kale ho gaye", set()), ("nikala", set()),
        ("urea dali", set()),
    ],
)
def test_exact_days_named(clause: str, days: set[int]) -> None:
    assert parser.exact_days_named(clause) == days


# --- units and products --------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("bori", "bori"), ("Boriyan", "bori"), ("BAGS", "bori"), ("بوری", "bori"),
        ("بوریاں", "bori"),
        ("kg", "kg"), ("KGs", "kg"), ("Kilo", "kg"), ("کلو", "kg"), ("کلوگرام", "kg"),
        ("Litre", "litre"), ("litres", "litre"), ("Liters", "litre"), ("لیٹر", "litre"),
        ("ml", "ml"), ("ملی لیٹر", "ml"),
        ("tanki", "tanki"), ("Tank", "tanki"), ("ٹنکی", "tanki"), ("ٹینکی", "tanki"),
        ("ٹنکیاں", "tanki"), ("ٹینکیاں", "tanki"),
        ("mm", "mm"), ("ملی میٹر", "mm"), ("Killa", "acre"), ("kanal", "kanal"),
        ("  kg ", "kg"),
    ],
)
def test_unit_aliases_map_to_canonical_units(raw: str, canonical: str) -> None:
    assert parser.normalize_unit_name(raw) == canonical


@pytest.mark.parametrize(("raw", "expected"), [("Widget", "widget"), ("", None), ("  ", None),
                                               (None, None)])
def test_unknown_units_pass_through_and_blank_units_are_null(
    raw: str | None, expected: str | None
) -> None:
    assert parser.normalize_unit_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("urea", "urea"), ("Urea", "urea"), ("UREA", "urea"), ("یوریا", "urea"),
        ("  urea ", "urea"),
        ("DAP", "DAP"), ("dap", "DAP"), ("D.A.P", "DAP"), ("ڈی اے پی", "DAP"),
        ("spray", "spray"), ("Spray", "spray"), ("سپرے", "spray"), ("اسپرے", "spray"),
        ("rainfall", "rainfall"), ("Rain", "rainfall"), ("barish", "rainfall"),
        ("بارش", "rainfall"),
        ("wheat", "wheat"), ("Gandum", "wheat"), ("گندم", "wheat"),
        ("tomato", "tomato"), ("Tamatar", "tomato"), ("ٹماٹر", "tomato"),
    ],
)
def test_product_aliases_map_to_canonical_products(raw: str, canonical: str) -> None:
    assert parser.normalize_product_name(raw) == canonical


@pytest.mark.parametrize(("raw", "expected"), [("  Potash ", "Potash"), ("", None), ("  ", None),
                                               (None, None)])
def test_unknown_products_pass_through_trimmed_and_blank_products_are_null(
    raw: str | None, expected: str | None
) -> None:
    assert parser.normalize_product_name(raw) == expected


def test_alias_tables_map_lowercase_keys_onto_the_canonical_names() -> None:
    tables = ((parser.UNIT_ALIASES, CANONICAL_UNITS, parser.normalize_unit_name),
              (parser.PRODUCT_ALIASES, CANONICAL_PRODUCTS, parser.normalize_product_name))
    for table, canonical, normalize in tables:
        assert set(table.values()) == canonical
        for alias in table:
            assert alias == " ".join(alias.split()).lower(), alias  # reachable by the lookup
        for name in canonical:
            assert normalize(name) == name


def test_few_shot_and_sample_csv_already_use_the_canonical_names() -> None:
    products: set[str] = set()
    units: set[str] = set()
    for _, output in parser.FEW_SHOT:
        products |= {e["product"] for e in output["events"] if e["product"]}
        units |= {e["unit"] for e in output["events"] if e["unit"]}
    with SAMPLE_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            products |= {row["product"]} - {""}
            units |= {row["unit"]} - {""}
    assert products <= CANONICAL_PRODUCTS
    assert units <= CANONICAL_UNITS


def test_parse_normalizes_products_and_units() -> None:
    note = "pichle hafte 1 bori Urea dali, aaj 2 بوریاں یوریا"
    result, _ = parse(note, reply(ev("fertilizer", 7, product="Urea", quantity=1, unit="Bori"),
                                  ev("fertilizer", 0, product="یوریا", quantity=2, unit="بوریاں")))
    assert [(e.product, e.quantity, e.unit) for e in result.events] == [
        ("urea", 1, "bori"), ("urea", 2, "bori")]


def test_spellings_of_one_product_are_compared_by_the_engine(session: Session) -> None:
    farm = Farm(name="F")
    session.add(farm)
    session.flush()
    field = Field(farm_id=farm.id, name="North", crop="tomato")
    session.add(field)
    session.flush()
    first, _ = parse("10 din pehle 1 bori Urea dali",
                     reply(ev("fertilizer", 10, product="Urea", quantity=1, unit="bori")))
    second, _ = parse("aaj do بوریاں یوریا ڈالی",
                      reply(ev("fertilizer", 0, product="یوریا", quantity=2, unit="بوریاں")))
    for proposal in first.events + second.events:  # the farmer confirms both proposals
        assert proposal.occurred_at is not None
        create_event(session, field_id=field.id, type=EventType(proposal.type),
                     occurred_at=proposal.occurred_at,
                     date_certainty=DateCertainty(proposal.date_certainty),
                     product=proposal.product, quantity=proposal.quantity, unit=proposal.unit,
                     source=EventSource.farmer_text, today=TODAY)
    session.commit()
    [comparison] = compare_values(session, field.id, EventType.fertilizer)
    assert comparison.product == "urea"
    assert comparison.percent_change == 100.0


# --- LLM call, validation and the single retry ----------------------------------------------

def test_the_json_schema_is_passed_to_the_llm() -> None:
    _, llm = parse("aaj pani diya", reply(ev("irrigation", 0)))
    [call] = llm.calls
    assert call["json_schema"] == parser.ModelOutput.model_json_schema()
    assert call["tools"] is None


def test_invalid_json_is_retried_once_then_accepted() -> None:
    bad = "sorry, here it is: {events: ["
    good = reply(ev("fertilizer", 0, product="urea", quantity=2, unit="bori"))
    result, llm = parse("aaj 2 bori urea dali", bad, good)
    assert result.error is None
    assert result.attempts == 2
    assert [(e.product, e.quantity, e.unit) for e in result.events] == [("urea", 2, "bori")]
    assert len(llm.calls) == 2
    retry = llm.calls[1]
    assert retry["json_schema"] == parser.ModelOutput.model_json_schema()
    assert retry["messages"][-2] == {"role": "assistant", "content": bad}
    assert retry["messages"][-1]["role"] == "user"
    assert "invalid" in retry["messages"][-1]["content"]


def test_two_invalid_replies_give_an_error_and_no_events() -> None:
    result, llm = parse("aaj urea dali", "not json", '{"events": [{"type": "disease"}]}')
    assert result.events == []
    assert result.attempts == 2
    assert result.error is not None
    assert result.error.startswith("invalid model output after retry")
    assert len(llm.calls) == 2


@pytest.mark.parametrize("bad", [{"quantity": -2}, {"days_ago": 366}],
                         ids=["negative-quantity", "days-ago-over-365"])
def test_an_out_of_range_value_is_sent_back_for_correction(bad: dict[str, int]) -> None:
    good = ev("fertilizer", 0, product="urea", quantity=2, unit="bori")
    result, llm = parse("aaj 2 bori urea dali", reply({**good, **bad}), reply(good))
    assert result.attempts == 2
    [event] = result.events
    assert (event.quantity, event.occurred_at) == (2, TODAY)
    [field] = bad
    assert field in llm.calls[1]["messages"][-1]["content"]  # the validation error names it


def test_out_of_range_values_never_come_back_as_data() -> None:
    result, _ = parse("aaj 2 bori urea dali", reply(ev("fertilizer", 0, quantity=-2)),
                      reply(ev("fertilizer", 400, quantity=2)))
    assert result.events == []
    assert result.attempts == 2
    assert result.error is not None
    assert result.error.startswith("invalid model output after retry")


@pytest.mark.parametrize(
    ("failure", "error"),
    [(ProviderResponseError("groq llm status 429"), "bad_response: groq llm status 429"),
     (ConnectionError("connection refused"), "unavailable: ConnectionError")],
    ids=["bad-response", "unavailable"],
)
def test_a_provider_error_gives_an_error_and_no_events(failure: Exception, error: str) -> None:
    result, llm = parse("aaj pani diya", failure)
    assert result.events == []
    assert result.error == error
    assert result.attempts == 1
    assert len(llm.calls) == 1  # a provider failure is not retried


def test_a_provider_error_on_the_retry_gives_an_error_and_no_events() -> None:
    result, _ = parse("aaj pani diya", "not json", ProviderResponseError("groq llm status 503"))
    assert result.events == []
    assert result.error == "bad_response: groq llm status 503"
    assert result.attempts == 2


def test_an_empty_events_list_is_accepted() -> None:
    result, llm = parse("salam, kya haal hai", '{"events": []}')
    assert result.events == []
    assert result.error is None
    assert result.attempts == 1
    assert len(llm.calls) == 1


def test_json_inside_a_code_fence_is_accepted() -> None:
    result, _ = parse("kal pani diya", "```json\n" + reply(ev("irrigation", 1)) + "\n```")
    assert result.attempts == 1
    assert [e.occurred_at for e in result.events] == [date(2026, 3, 14)]


# --- the model never returns a calendar date ------------------------------------------------

def test_the_model_schema_has_no_calendar_date_field() -> None:
    assert set(parser.ModelEvent.model_fields) == MODEL_FIELDS
    schema = json.dumps(parser.ModelOutput.model_json_schema())
    assert '"format": "date' not in schema  # neither date nor date-time
    assert "occurred_at" not in schema


def test_a_calendar_date_sent_by_the_model_is_ignored() -> None:
    sneaky = {**ev("irrigation", 1), "date": "2020-01-01", "occurred_at": "2020-01-01"}
    result, _ = parse("kal pani diya", reply(sneaky))
    [event] = result.events
    assert event.occurred_at == date(2026, 3, 14)


# --- prompt -------------------------------------------------------------------------------

def test_few_shot_examples_cover_the_languages_and_agri_words() -> None:
    texts = [text for text, _ in parser.FEW_SHOT]
    assert 12 <= len(texts) <= 15
    assert any(URDU_SCRIPT.search(t) for t in texts)
    assert any(t.isascii() and re.search(r"\b(aaj|kal|parson|pichle)\b", t) for t in texts)
    assert any(re.search(r"\b(today|yesterday)\b", t, re.I) for t in texts)
    corpus = " ".join(texts).lower()
    for word in ("urea", "dap", "pani", "spray", "patta peela", "bori", "tanki"):
        assert word in corpus, word


def test_few_shot_outputs_follow_the_model_schema() -> None:
    for text, output in parser.FEW_SHOT:
        parser.ModelOutput.model_validate(output)
        for event in output["events"]:
            assert set(event) <= MODEL_FIELDS, text


def test_messages_hold_the_system_prompt_and_every_few_shot_pair_in_order() -> None:
    messages = parser.build_messages("aaj pani diya", TODAY)
    assert messages[0] == {"role": "system", "content": parser.SYSTEM_PROMPT}
    pairs = messages[1:-1]
    assert len(pairs) == 2 * len(parser.FEW_SHOT)
    for i, (text, output) in enumerate(parser.FEW_SHOT):
        assert pairs[2 * i] == {"role": "user", "content": text}
        assert pairs[2 * i + 1]["role"] == "assistant"
        assert json.loads(pairs[2 * i + 1]["content"]) == output


def test_the_last_user_message_carries_today_and_the_field_names() -> None:
    _, llm = parse("aaj pani diya", reply(ev("irrigation", 0)), field_names=["North", "South"])
    last = llm.calls[0]["messages"][-1]
    assert last["role"] == "user"
    assert "2026-03-15" in last["content"]
    assert "North" in last["content"]
    assert "South" in last["content"]
    assert last["content"].endswith("aaj pani diya")


# --- proposals only -----------------------------------------------------------------------

def test_parse_returns_proposals_and_has_no_db_access() -> None:
    llm = FakeLLM(replies=[reply(ev("fertilizer", 0, product="urea", quantity=2, unit="bori"))])
    result = parser.parse_text("aaj 2 bori urea dali", TODAY, llm, source="farmer_voice")
    [event] = result.events
    assert isinstance(event, parser.ProposedEvent)
    assert (event.raw_text, event.source) == ("aaj 2 bori urea dali", "farmer_voice")
    assert "display_id" not in parser.ProposedEvent.model_fields  # no E-### until saved
    assert "session" not in inspect.signature(parser.parse_text).parameters
    tree = ast.parse(Path(parser.__file__).read_text(encoding="utf-8"))
    modules = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m.split(".")[0] for m in modules} & {"sqlalchemy", "app"}
