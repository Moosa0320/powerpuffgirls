"""Farmer text -> proposed events (guide 7.3). Nothing is saved until the farmer confirms.

The model returns days_ago, never a calendar date. Code resolves dates, normalizes units
and product names, validates with Pydantic and retries once on invalid output.

Date certainty is set per event, in code, with no extra model field. The note is split into
clauses at punctuation and at aur/and, phir/then, lekin/magar/but (اور/پھر/لیکن/مگر).
A clause with a vague marker ("pichle hafte", "takreeban", "مہینے") is vague. The other
clauses name exact days: aaj/today/آج = 0, kal/yesterday/کل = 1, parson/day before
yesterday/پرسوں = 2 and "N din/days/دن pehle/ago/پہلے" = N. An event is approximate when the
note has a vague clause and its days_ago is not one of those exact days; otherwise it is
exact. A null days_ago is "unknown".

Known limitations (the farmer reviews every proposal before anything is saved):
- A hedge about something other than the date still makes its clause vague: in
  "kal about 40 mm barish hui" the rain event is approximate.
- Events are not tied to clauses. When a vague clause and an exact clause give the same
  days_ago, both events are exact. An event whose day is implied rather than named (no day
  word in its clause) is approximate when another clause is vague.
- Only digits count as N ("do din pehle" names no exact day), and vague phrases outside the
  marker list ("kal ya parson", "do teen din") are not detected.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.engine import resolve_days_ago
from harness.jsonutil import extract_json_text
from harness.llm.base import LLMProvider

ModelEventType = Literal["planting", "irrigation", "fertilizer", "pesticide", "weather",
                         "observation", "harvest"]
Certainty = Literal["exact", "approximate", "unknown"]

# Keys are lowercase with single spaces. Values are the canonical names used by the engine,
# the few-shot examples and the skill's examples/sample_farm.csv.
UNIT_ALIASES = {
    "bori": "bori", "boriyan": "bori", "bag": "bori", "bags": "bori",
    "بوری": "bori", "بوریاں": "bori",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "کلو": "kg", "کلوگرام": "kg", "کلو گرام": "kg",
    "litre": "litre", "litres": "litre", "liter": "litre", "liters": "litre", "ltr": "litre",
    "l": "litre", "لیٹر": "litre",
    "ml": "ml", "ملی لیٹر": "ml",
    "tanki": "tanki", "tankiyan": "tanki", "tank": "tanki", "tanks": "tanki",
    "ٹنکی": "tanki", "ٹینکی": "tanki", "ٹنکیاں": "tanki", "ٹینکیاں": "tanki",
    "acre": "acre", "acres": "acre", "killa": "acre", "ایکڑ": "acre",
    "kanal": "kanal", "کنال": "kanal",
    "mm": "mm", "ملی میٹر": "mm",
}
# engine.compare_values groups by the exact product string, so every spelling of a product
# must reach one canonical name before the farmer confirms it.
PRODUCT_ALIASES = {
    "urea": "urea", "uria": "urea", "yuria": "urea", "yoria": "urea", "یوریا": "urea",
    "dap": "DAP", "d.a.p": "DAP", "d.a.p.": "DAP", "d a p": "DAP", "ڈی اے پی": "DAP",
    "spray": "spray", "sprey": "spray", "spre": "spray", "سپرے": "spray", "اسپرے": "spray",
    "rainfall": "rainfall", "rain": "rainfall", "barish": "rainfall", "baarish": "rainfall",
    "barsaat": "rainfall", "بارش": "rainfall", "برسات": "rainfall",
    "wheat": "wheat", "gandum": "wheat", "gandam": "wheat", "گندم": "wheat",
    "tomato": "tomato", "tomatoes": "tomato", "tamatar": "tomato", "tamater": "tomato",
    "ٹماٹر": "tomato",
}

# Vague date words, matched as substrings: "تقریبا" also covers "تقریباً", "week" covers "weeks".
APPROXIMATE_MARKERS = re.compile(
    r"(hafta|hafte|haftay|hafton|week|mahina|mahine|mahinay|mahinon|month|takreeban|"
    r"taqreeban|takriban|taqriban|lagbhag|about|around|kuch din|"
    r"ہفتہ|ہفتے|ہفتوں|مہینہ|مہینے|مہینوں|تقریبا|لگ بھگ|کچھ دن)",
    re.I)
# Clause breaks: punctuation and conjunctions. A point only breaks before a space or the end
# (so "2.5" and "D.A.P" stay whole); a comma breaks unless it sits inside a number like 1,5.
_CLAUSE_BREAK = re.compile(
    r"[;!?\n۔،؛؟]|\.(?!\S)|(?<!\d),|,(?!\d)"
    r"|(?<!\w)(?:aur|and|phir|then|lekin|magar|but|اور|پھر|لیکن|مگر)(?!\w)",
    re.I)
# Exact day words. Whole words only, so "kale", "nikala" and "کلو" do not count as "kal"/"کل".
# "day before yesterday" comes before "yesterday" so it is read as one phrase.
_EXACT_DAY = re.compile(
    r"(?<!\w)(?:(?P<n>\d{1,3})\s*(?:din|days?|دن)\s*(?:pehle|pehlay|pahle|ago|back|پہلے)"
    r"|(?P<two>day before yesterday|parson|parso|پرسوں)"
    r"|(?P<one>yesterday|kal|کل)"
    r"|(?P<zero>today|aaj|aj|آج))(?!\w)",
    re.I)
_NAMED_DAY = {"zero": 0, "one": 1, "two": 2}


class ModelEvent(BaseModel):
    """What the LLM is allowed to return. Never a calendar date."""

    model_config = ConfigDict(extra="ignore")
    type: ModelEventType
    product: str | None = None
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = None
    days_ago: int | None = Field(default=None, ge=0, le=365)
    symptom: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ModelOutput(BaseModel):
    events: list[ModelEvent]


class ProposedEvent(BaseModel):
    type: str
    product: str | None
    quantity: float | None
    unit: str | None
    occurred_at: date | None
    date_certainty: Certainty
    symptom: str | None
    confidence: float | None
    raw_text: str
    source: str


class ParseResult(BaseModel):
    events: list[ProposedEvent] = []
    error: str | None = None
    attempts: int = 0


SYSTEM_PROMPT = (
    "You extract farm events from a farmer's note written in Urdu script, Roman Urdu, English or a mix.\n"
    'Return JSON: {"events": [...]}. Each event has: type (planting|irrigation|fertilizer|pesticide|'
    "weather|observation|harvest), product, quantity, unit, days_ago, symptom, confidence (0-1).\n"
    "Rules:\n"
    "- Never guess. Unknown product, quantity, unit or date is null.\n"
    "- Never output a calendar date. Use days_ago: aaj/today=0, kal/yesterday=1, parson=2, "
    "pichle hafte/last week=7.\n"
    "- Give each event its own days_ago from the words about that event.\n"
    "- symptom only on observation events, in the farmer's own words.\n"
    "- Do not diagnose and do not name diseases.\n"
    '- If the note has no farm event, return {"events": []}.'
)

FEW_SHOT: list[tuple[str, dict[str, Any]]] = [
    ("aaj 2 bori urea dali", {"events": [{"type": "fertilizer", "product": "urea", "quantity": 2,
     "unit": "bori", "days_ago": 0, "symptom": None, "confidence": 0.95}]}),
    ("kal khet ko pani diya", {"events": [{"type": "irrigation", "product": None, "quantity": None,
     "unit": None, "days_ago": 1, "symptom": None, "confidence": 0.9}]}),
    ("parson spray kiya tha", {"events": [{"type": "pesticide", "product": "spray", "quantity": None,
     "unit": None, "days_ago": 2, "symptom": None, "confidence": 0.8}]}),
    ("pichle hafte DAP ki ek bori", {"events": [{"type": "fertilizer", "product": "DAP", "quantity": 1,
     "unit": "bori", "days_ago": 7, "symptom": None, "confidence": 0.85}]}),
    ("tamatar ke patte peele ho rahe hain", {"events": [{"type": "observation", "product": None,
     "quantity": None, "unit": None, "days_ago": 0, "symptom": "patte peele", "confidence": 0.9}]}),
    ("آج دو بوری یوریا ڈالی", {"events": [{"type": "fertilizer", "product": "urea", "quantity": 2,
     "unit": "bori", "days_ago": 0, "symptom": None, "confidence": 0.95}]}),
    ("کل کھیت کو پانی دیا", {"events": [{"type": "irrigation", "product": None, "quantity": None,
     "unit": None, "days_ago": 1, "symptom": None, "confidence": 0.9}]}),
    ("پتے پیلے ہو گئے ہیں", {"events": [{"type": "observation", "product": None, "quantity": None,
     "unit": None, "days_ago": 0, "symptom": "پتے پیلے", "confidence": 0.9}]}),
    ("Gave 1 tanki water yesterday and applied urea today", {"events": [
        {"type": "irrigation", "product": None, "quantity": 1, "unit": "tanki", "days_ago": 1,
         "symptom": None, "confidence": 0.9},
        {"type": "fertilizer", "product": "urea", "quantity": None, "unit": None, "days_ago": 0,
         "symptom": None, "confidence": 0.85}]}),
    ("kal bohat barish hui", {"events": [{"type": "weather", "product": "rainfall", "quantity": None,
     "unit": None, "days_ago": 1, "symptom": None, "confidence": 0.85}]}),
    ("3 din pehle 2 tanki spray ki", {"events": [{"type": "pesticide", "product": "spray",
     "quantity": 2, "unit": "tanki", "days_ago": 3, "symptom": None, "confidence": 0.85}]}),
    ("pani diya tha kab yaad nahi", {"events": [{"type": "irrigation", "product": None,
     "quantity": None, "unit": None, "days_ago": None, "symptom": None, "confidence": 0.6}]}),
    ("aaj gandum ki katai shuru ki", {"events": [{"type": "harvest", "product": "wheat",
     "quantity": None, "unit": None, "days_ago": 0, "symptom": None, "confidence": 0.9}]}),
    ("pattay murjha rahe hain aur kuch dhabbe hain", {"events": [{"type": "observation",
     "product": None, "quantity": None, "unit": None, "days_ago": 0,
     "symptom": "pattay murjha rahe, dhabbe", "confidence": 0.85}]}),
    ("pichle hafte DAP dali aur aaj patta peela dikha", {"events": [
        {"type": "fertilizer", "product": "DAP", "quantity": None, "unit": None, "days_ago": 7,
         "symptom": None, "confidence": 0.8},
        {"type": "observation", "product": None, "quantity": None, "unit": None, "days_ago": 0,
         "symptom": "patta peela", "confidence": 0.85}]}),
]


def build_messages(text: str, today: date, field_names: list[str] | None = None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for example_text, example_out in FEW_SHOT:
        messages.append({"role": "user", "content": example_text})
        messages.append({"role": "assistant", "content": json.dumps(example_out, ensure_ascii=False)})
    context = f"Today is {today.isoformat()}."
    if field_names:
        context += " Fields: " + ", ".join(field_names) + "."
    messages.append({"role": "user", "content": f"{context}\nNote: {text}"})
    return messages


def _alias_key(name: str) -> str:
    return " ".join(name.split()).lower()


def normalize_unit_name(unit: str | None) -> str | None:
    """Canonical unit name. Unknown units pass through lowercased; blank means unknown."""
    if unit is None or not unit.strip():
        return None
    key = _alias_key(unit)
    return UNIT_ALIASES.get(key, key)


def normalize_product_name(product: str | None) -> str | None:
    """Canonical product name, ignoring case. Unknown products pass through trimmed."""
    if product is None or not product.strip():
        return None
    return PRODUCT_ALIASES.get(_alias_key(product), product.strip())


def split_clauses(text: str) -> list[str]:
    """Split a note at punctuation and at conjunctions such as aur, phir, lekin, اور, مگر."""
    return [part.strip() for part in _CLAUSE_BREAK.split(text) if part.strip()]


def exact_days_named(clause: str) -> set[int]:
    """Exact days ago named in a clause: aaj 0, kal 1, parson 2, "N din pehle" N.

    Roman Urdu, English (today, yesterday, N days ago) and Urdu script (آج, کل, پرسوں, N دن پہلے).
    """
    days: set[int] = set()
    for match in _EXACT_DAY.finditer(clause):
        n = match["n"]
        days.add(int(n) if n is not None else _NAMED_DAY[str(match.lastgroup)])
    return days


def date_certainty(days_ago: int | None, text: str) -> Certainty:
    """Certainty of one event's date, judged from the clauses of its note (see module doc)."""
    if days_ago is None:
        return "unknown"
    vague = False
    exact: set[int] = set()
    for clause in split_clauses(text):
        if APPROXIMATE_MARKERS.search(clause):
            vague = True
        else:
            exact |= exact_days_named(clause)
    return "approximate" if vague and days_ago not in exact else "exact"


def _to_proposal(e: ModelEvent, text: str, today: date, source: str) -> ProposedEvent:
    occurred = None if e.days_ago is None else resolve_days_ago(e.days_ago, today)
    return ProposedEvent(type=e.type, product=normalize_product_name(e.product),
                         quantity=e.quantity, unit=normalize_unit_name(e.unit),
                         occurred_at=occurred, date_certainty=date_certainty(e.days_ago, text),
                         symptom=e.symptom, confidence=e.confidence, raw_text=text, source=source)


def parse_text(text: str, today: date, llm: LLMProvider, source: str = "farmer_text",
               field_names: list[str] | None = None) -> ParseResult:
    messages = build_messages(text, today, field_names)
    schema = ModelOutput.model_json_schema()
    last_error = ""
    for attempt in (1, 2):  # one retry on invalid output
        res = llm.chat(messages, json_schema=schema)
        if not res.ok or res.value is None:
            err = res.error
            return ParseResult(error=f"{err.kind}: {err.message}" if err else "LLM failed", attempts=attempt)
        content = res.value.content
        try:
            output = ModelOutput.model_validate_json(extract_json_text(content))
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)[:300]
            messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That output was invalid: {last_error}\nReturn only corrected JSON."},
            ]
            continue
        return ParseResult(events=[_to_proposal(e, text, today, source) for e in output.events],
                           attempts=attempt)
    return ParseResult(error=f"invalid model output after retry: {last_error}", attempts=2)
