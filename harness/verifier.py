"""Report verifier (guide 7.6). Pure code: no AI, no network.

Rejects: unknown or foreign citations, IDs in prose that are not cited, dates or
quantities that do not match the cited records, diagnosis or cause-as-fact wording,
treatment or dosage recommendations, unlabelled unconfirmed photo observations,
an empty missing-records section when gaps exist, uncited facts, a missing disclaimer.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from harness.engine import GapReport, TimelineItem, normalize_unit

SECTIONS = ("records_show", "worth_investigating", "questions_next", "missing_records",
            "photo_observations")
CLAIM_TYPES = {"fact", "possibility", "question"}
DISCLAIMER = "This is an evidence summary built from records, not a diagnosis."
SKILL_DIR = Path(__file__).resolve().parents[1] / "skill" / "farm-record-investigation"
BANNED_CLAIMS_FILE = SKILL_DIR / "references" / "banned-claims.md"

_ID_RE = re.compile(r"\b([EP])-(\d{3,})\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|gram|g|bori|bag|litre|liter|ml|l|tanki|mm)\b", re.I)
_PCT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_UNCONFIRMED_MARKERS = ("unconfirmed", "not confirmed", "tasdeeq nahi", "غیر تصدیق شدہ")

DEFAULT_BANNED = [
    r"\b(is|was|are|were)\s+caused\s+by\b", r"\bcaused\s+by\b", r"\bdefinitely\b",
    r"\bcertainly\b", r"\bdeficiency\s+of\b",
    r"\b(has|have|is|are)\s+(an?\s+)?(infection|blight|rust|mildew|virus|rot|fungus|disease)\b",
    r"\b(infected|suffering)\s+(with|from)\b", r"\bthe\s+(cause|disease|problem)\s+is\b",
    r"\b(ye|yeh|yah)\s+bimari\s+hai\b", r"\bbimari\s+hai\b", r"\bki\s+wajah\s+se\s+(hai|hua|hui)\b",
    r"\b(pakka|yaqeenan|yakeenan)\b", r"\bki\s+kami\s+(hai|hui)\b",
]
# Checked on every claim.
RECOMMENDATION_PATTERNS = [re.compile(p, re.I) for p in (
    r"\b(should|must|needs?\s+to|ought\s+to)\s+(be\s+)?(apply|applied|spray|sprayed|use|used|add|added)\b",
    r"\brecommend\w*\b[^.]*\b(pesticide|fungicide|insecticide|herbicide|spray|dose|dosage)\b",
    r"\b(spray|dawai|khad)\s+(karein|karo|karen|kijiye|dalein|daalein|dalo)\b",
    r"(اسپرے|دوائی|دوا) (کریں|ڈالیں)", r"استعمال کریں",
)]
# Checked on possibilities and questions only (facts may quote a recorded dose).
NONFACT_RECOMMENDATION_PATTERNS = [re.compile(p, re.I) for p in (
    r"(^|[.;!]\s*)(please\s+)?(apply|spray|mix)\s",
    r"\b\d+(\.\d+)?\s*(ml|g|gram|kg|litre|liter|l|bori)\s*(per|/)\s*(acre|litre|liter|tanki|kanal)\b",
    r"\b(pesticide|fungicide|insecticide)\b[^.]*\b(apply|spray|use)\b",
)]


@dataclass(frozen=True)
class EventFact:
    display_id: str
    occurred_at: date
    type: str
    product: str | None = None
    quantity: float | None = None
    unit: str | None = None


@dataclass
class Evidence:
    """Everything a report may be checked against, for ONE field."""

    events: dict[str, EventFact]
    photos: dict[str, bool]  # display_id -> verified_by_farmer
    gaps_found: bool
    symptom_date: date | None = None


@dataclass
class VerificationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def load_banned_patterns(path: Path = BANNED_CLAIMS_FILE) -> list[re.Pattern[str]]:
    """Patterns come from the skill's references/banned-claims.md, with built-in defaults."""
    sources: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*-\s*regex:\s*`(.+)`\s*$", line)
            if m:
                sources.append(m.group(1))
    return [re.compile(p, re.I) for p in (sources or DEFAULT_BANNED)]


def _qty_matches(value: float, unit: str, e: EventFact) -> bool:
    if e.quantity is None:
        return False
    if abs(e.quantity - value) < 1e-6 and (e.unit is None or e.unit.lower() == unit.lower()):
        return True
    a, ua = normalize_unit(value, unit)
    b, ub = normalize_unit(e.quantity, e.unit)
    return a is not None and b is not None and ua == ub and abs(a - b) < 1e-6


def _percent_changes(cited: list[EventFact]) -> set[float]:
    out: set[float] = set()
    for a, b in itertools.combinations(sorted(cited, key=lambda e: e.occurred_at), 2):
        if a.type != b.type or a.quantity is None or b.quantity is None:
            continue
        va, ua = normalize_unit(a.quantity, a.unit)
        vb, ub = normalize_unit(b.quantity, b.unit)
        if ua == ub and va:
            out.add(round(abs((vb - va) / va * 100), 1))
    return out


def _check_numbers(where: str, text: str, cited: list[EventFact], ev: Evidence) -> list[str]:
    errs: list[str] = []
    allowed_dates = {e.occurred_at.isoformat() for e in cited}
    if ev.symptom_date is not None:
        allowed_dates.add(ev.symptom_date.isoformat())
    for d in _ISO_DATE_RE.findall(text):
        if d not in allowed_dates:
            errs.append(f"{where}: date {d} does not match any cited record")
    for num, unit in _QTY_RE.findall(text):
        if not any(_qty_matches(float(num), unit, e) for e in cited):
            errs.append(f"{where}: quantity {num} {unit} does not match any cited record")
    pcts = _percent_changes(cited)
    for p in _PCT_RE.findall(text):
        if round(abs(float(p)), 1) not in pcts:
            errs.append(f"{where}: {p}% does not match a change between cited records")
    return errs


def _check_claim(section: str, i: int, claim: Any, ev: Evidence,
                 banned: list[re.Pattern[str]]) -> list[str]:
    where = f"{section}[{i}]"
    if not isinstance(claim, dict):
        return [f"{where}: claim is not an object"]
    text, ctype = claim.get("text"), claim.get("type")
    event_ids, photo_ids = claim.get("event_ids") or [], claim.get("photo_ids") or []
    if not isinstance(text, str) or not text.strip():
        return [f"{where}: empty text"]
    if not isinstance(event_ids, list) or not isinstance(photo_ids, list):
        return [f"{where}: event_ids and photo_ids must be lists"]
    errs: list[str] = []
    if ctype not in CLAIM_TYPES:
        errs.append(f"{where}: type must be fact, possibility or question")
    for eid in event_ids:
        if eid not in ev.events:
            errs.append(f"{where}: cited event {eid} does not exist for this field")
    for pid in photo_ids:
        if pid not in ev.photos:
            errs.append(f"{where}: cited photo {pid} does not exist for this field")
    for prefix, num in _ID_RE.findall(text):
        ref = f"{prefix}-{num}"
        if ref not in (event_ids if prefix == "E" else photo_ids):
            errs.append(f"{where}: text mentions {ref} but does not cite it")
    if ctype == "fact" and section != "missing_records" and not event_ids and not photo_ids:
        errs.append(f"{where}: fact has no citation")
    for pat in banned:
        if pat.search(text):
            errs.append(f"{where}: diagnosis or cause-as-fact wording (/{pat.pattern}/)")
            break
    patterns = RECOMMENDATION_PATTERNS + ([] if ctype == "fact" else NONFACT_RECOMMENDATION_PATTERNS)
    if any(p.search(text) for p in patterns):
        errs.append(f"{where}: treatment or dosage recommendation")
    cited = [ev.events[e] for e in event_ids if e in ev.events]
    errs.extend(_check_numbers(where, text, cited, ev))
    if section == "photo_observations":
        if not photo_ids:
            errs.append(f"{where}: photo observation cites no photo")
        unverified = [p for p in photo_ids if p in ev.photos and not ev.photos[p]]
        labelled = claim.get("unconfirmed") is True or any(
            m in text.lower() for m in _UNCONFIRMED_MARKERS)
        if unverified and not labelled:
            errs.append(f"{where}: unverified photo observation must be labelled unconfirmed")
    return errs


def verify_report(report: Any, evidence: Evidence,
                  banned: list[re.Pattern[str]] | None = None) -> VerificationResult:
    if not isinstance(report, dict):
        return VerificationResult(False, ["report is not a JSON object"])
    sections = report.get("sections")
    if not isinstance(sections, dict):
        return VerificationResult(False, ["report.sections is missing"])
    banned = load_banned_patterns() if banned is None else banned
    errors: list[str] = []
    for name in SECTIONS:
        claims = sections.get(name)
        if not isinstance(claims, list):
            errors.append(f"section '{name}' is missing or not a list")
            continue
        for i, claim in enumerate(claims):
            errors.extend(_check_claim(name, i, claim, evidence, banned))
    if evidence.gaps_found and not sections.get("missing_records"):
        errors.append("missing_records is empty but find_gaps returned gaps")
    if report.get("disclaimer") != DISCLAIMER:
        errors.append("disclaimer is missing or altered")
    return VerificationResult(ok=not errors, errors=errors)


def safe_template_report(timeline: list[TimelineItem], gaps: GapReport, window_days: int) -> dict[str, Any]:
    """Code-written report used when the model fails verification. No model prose."""
    records: list[dict[str, Any]] = []
    photos: list[dict[str, Any]] = []
    for item in timeline:
        day = item.occurred_at.isoformat()
        if item.kind == "photo":
            photos.append({"text": f"Photo {item.display_id} was taken on {day}; any visible "
                                   "symptoms are unconfirmed.", "type": "fact", "event_ids": [],
                           "photo_ids": [item.display_id], "unconfirmed": True})
            continue
        details = [d for d in (item.product,
                               (f"{item.quantity:g} {item.unit}" if item.unit else f"{item.quantity:g}")
                               if item.quantity is not None else None) if d]
        text = f"{day}: {item.type} recorded"
        if details:
            text += f" ({', '.join(details)})"
        if item.symptom:
            text += f'; farmer reported "{item.symptom}"'
        text += f" ({item.display_id})."
        if item.type == "weather":
            text += " Weather data is area-level, not field-level."
        records.append({"text": text, "type": "fact", "event_ids": [item.display_id], "photo_ids": []})

    missing: list[dict[str, Any]] = []
    for flag, label in ((gaps.missing_irrigation, "irrigation"),
                        (gaps.missing_fertilizer, "fertilizer"),
                        (gaps.missing_weather, "weather")):
        if flag:
            missing.append({"text": f"No {label} record in the {window_days} days before the "
                                    f"symptom, so {label} effects cannot be concluded.",
                            "type": "fact", "event_ids": [], "photo_ids": []})
    for eid in gaps.null_quantity_events:
        missing.append({"text": f"Quantity was not recorded for {eid}.", "type": "fact",
                        "event_ids": [eid], "photo_ids": []})
    for eid in gaps.unknown_date_events:
        missing.append({"text": f"The date of {eid} is unknown, so it cannot be placed on the "
                                "timeline.", "type": "fact", "event_ids": [eid], "photo_ids": []})
    return {
        "sections": {
            "records_show": records,
            "worth_investigating": [{"text": "An agricultural expert may be worth consulting if the "
                                             "symptom spreads or persists.", "type": "possibility",
                                     "event_ids": [], "photo_ids": []}],
            "questions_next": [{"text": "Has the symptom spread to other plants or fields since it "
                                        "was first seen?", "type": "question", "event_ids": [],
                                "photo_ids": []}],
            "missing_records": missing,
            "photo_observations": photos,
        },
        "disclaimer": DISCLAIMER,
    }