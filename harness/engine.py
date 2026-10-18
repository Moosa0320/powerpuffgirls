"""Engine: pure, deterministic analysis over farm records (guide section 7.4).

No AI, no network. These functions produce the FACTS that every report claim
must cite. Nulls mean unknown and drive gap detection.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend.models import Event, EventType, Photo

# --- Unit normalization lookup (guide section 5) ------------------------------
# Normalize to canonical units: mass->kg, volume->litre, area->acre.
# "bori" (a sack) is treated as 50 kg by convention; documented and overridable.
_UNIT_TO_CANONICAL: dict[str, tuple[str, float]] = {
    "kg": ("kg", 1.0),
    "g": ("kg", 0.001),
    "gram": ("kg", 0.001),
    "bori": ("kg", 50.0),
    "bag": ("kg", 50.0),
    "litre": ("litre", 1.0),
    "liter": ("litre", 1.0),
    "l": ("litre", 1.0),
    "ml": ("litre", 0.001),
    "tanki": ("litre", 200.0),  # a tank, ~200 L by convention
    "acre": ("acre", 1.0),
    "hectare": ("acre", 2.47105),
    "kanal": ("acre", 0.125),
}


def normalize_unit(quantity: float | None, unit: str | None) -> tuple[float | None, str | None]:
    """Return (canonical_quantity, canonical_unit). Unknown unit passes through."""
    if quantity is None or unit is None:
        return quantity, unit
    key = unit.strip().lower()
    if key not in _UNIT_TO_CANONICAL:
        return quantity, unit
    canonical_unit, factor = _UNIT_TO_CANONICAL[key]
    return quantity * factor, canonical_unit


def days_between(a: date, b: date) -> int:
    """Absolute number of days between two dates."""
    return abs((b - a).days)


def resolve_days_ago(days_ago: int, today: date) -> date:
    """Convert a model-provided days_ago into a calendar date (guide section 5)."""
    return today - timedelta(days=days_ago)


# --- Data carriers ------------------------------------------------------------
@dataclass(frozen=True)
class TimelineItem:
    kind: str  # "event" | "photo"
    display_id: str
    occurred_at: date
    type: str | None = None
    product: str | None = None
    quantity: float | None = None
    unit: str | None = None
    symptom: str | None = None


@dataclass
class GapReport:
    missing_irrigation: bool = False
    missing_fertilizer: bool = False
    missing_weather: bool = False
    null_quantity_events: list[str] = dc_field(default_factory=list)
    unknown_date_events: list[str] = dc_field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return (
            self.missing_irrigation
            or self.missing_fertilizer
            or self.missing_weather
            or bool(self.null_quantity_events)
            or bool(self.unknown_date_events)
        )


@dataclass(frozen=True)
class Comparison:
    event_id: str
    previous_event_id: str
    type: str
    product: str | None
    previous_value: float
    current_value: float
    unit: str | None
    percent_change: float | None


# --- Queries ------------------------------------------------------------------
def _events_in_window(
    session: Session, field_id: int, start: date | None, end: date | None
) -> list[Event]:
    stmt = select(Event).where(Event.field_id == field_id)
    if start is not None:
        stmt = stmt.where(Event.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(Event.occurred_at <= end)
    stmt = stmt.order_by(Event.occurred_at, Event.id)
    return list(session.execute(stmt).scalars())


def get_timeline(
    session: Session, field_id: int, start: date | None = None, end: date | None = None
) -> list[TimelineItem]:
    """Sorted events + photo observations in the window (guide 7.4)."""
    items: list[TimelineItem] = []
    for e in _events_in_window(session, field_id, start, end):
        items.append(
            TimelineItem(
                kind="event",
                display_id=e.display_id,
                occurred_at=e.occurred_at,
                type=e.type.value if e.type else None,
                product=e.product,
                quantity=e.quantity,
                unit=e.unit,
                symptom=e.symptom,
            )
        )
    photo_stmt = select(Photo).where(Photo.field_id == field_id)
    for p in session.execute(photo_stmt).scalars():
        taken = p.taken_at.date() if p.taken_at else None
        if taken is None:
            continue
        if start is not None and taken < start:
            continue
        if end is not None and taken > end:
            continue
        items.append(
            TimelineItem(kind="photo", display_id=p.display_id, occurred_at=taken, type="photo")
        )
    items.sort(key=lambda i: (i.occurred_at, i.display_id))
    return items


def find_gaps(
    session: Session, field_id: int, window_days: int, end: date | None = None
) -> GapReport:
    """Detect missing irrigation/fertilizer/weather records and incomplete events."""
    end = end or date.today()
    start = end - timedelta(days=window_days)
    events = _events_in_window(session, field_id, start, end)

    types_present = {e.type for e in events}
    report = GapReport(
        missing_irrigation=EventType.irrigation not in types_present,
        missing_fertilizer=EventType.fertilizer not in types_present,
        missing_weather=EventType.weather not in types_present,
    )
    for e in events:
        # quantity-bearing event types with a null quantity are a gap
        if e.type in {EventType.irrigation, EventType.fertilizer, EventType.pesticide}:
            if e.quantity is None:
                report.null_quantity_events.append(e.display_id)
        if e.date_certainty is not None and e.date_certainty.value == "unknown":
            report.unknown_date_events.append(e.display_id)
    return report


def compare_values(session: Session, field_id: int, type: EventType) -> list[Comparison]:
    """Change vs the previous record of the same (type, product), with % change."""
    stmt = (
        select(Event)
        .where(Event.field_id == field_id, Event.type == type)
        .order_by(Event.occurred_at, Event.id)
    )
    events = list(session.execute(stmt).scalars())
    comparisons: list[Comparison] = []
    last_by_product: dict[str | None, Event] = {}
    for e in events:
        prev = last_by_product.get(e.product)
        if prev is not None and prev.quantity is not None and e.quantity is not None:
            prev_val, _ = normalize_unit(prev.quantity, prev.unit)
            cur_val, cur_unit = normalize_unit(e.quantity, e.unit)
            pct: float | None
            if prev_val and prev_val != 0:
                pct = round((cur_val - prev_val) / prev_val * 100.0, 2)
            else:
                pct = None
            comparisons.append(
                Comparison(
                    event_id=e.display_id,
                    previous_event_id=prev.display_id,
                    type=type.value,
                    product=e.product,
                    previous_value=prev_val,
                    current_value=cur_val,
                    unit=cur_unit,
                    percent_change=pct,
                )
            )
        last_by_product[e.product] = e
    return comparisons