"""Farmer text -> proposed events (guide 7.3). Nothing is saved until the farmer confirms.

The model returns days_ago, never a calendar date. Code resolves dates, normalizes
units, validates with Pydantic and retries once on invalid output.
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

UNIT_ALIASES = {
    "bori": "bori", "boriyan": "bori", "bag": "bori", "bags": "bori", "بوری": "bori",
    "kg": "kg", "kilo": "kg", "kilogram": "kg", "کلو": "kg",
    "litre": "litre", "liter": "litre", "ltr": "litre", "l": "litre", "لیٹر": "litre",
    "ml": "ml", "tanki": "tanki", "tankiyan": "tanki", "ٹنکی": "tanki",
    "acre": "acre", "killa": "acre", "kanal": "kanal", "mm": "mm",
}
APPROXIMATE_MARKERS = re.compile(
    r"(hafte|hafta|week|takreeban|taqreeban|lagbhag|about|around|kuch din|mahine|month|ہفتے|تقریباً)",
    re.I)


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
    date_certainty: Literal["exact", "approximate", "unknown"]
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


def normalize_unit_name(unit: str | None) -> str | None:
    if unit is None or not unit.strip():
        return None
    key = unit.strip().lower()
    return UNIT_ALIASES.get(key, key)


def _to_proposal(e: ModelEvent, text: str, today: date, source: str) -> ProposedEvent:
    if e.days_ago is None:
        occurred, certainty = None, "unknown"
    else:
        occurred = resolve_days_ago(e.days_ago, today)
        certainty = "approximate" if APPROXIMATE_MARKERS.search(text) else "exact"
    return ProposedEvent(type=e.type, product=e.product, quantity=e.quantity,
                         unit=normalize_unit_name(e.unit), occurred_at=occurred,
                         date_certainty=certainty, symptom=e.symptom, confidence=e.confidence,
                         raw_text=text, source=source)


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