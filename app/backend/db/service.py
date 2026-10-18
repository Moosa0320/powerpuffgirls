"""DB-agnostic service helpers: display-ID generation and validation.

Kept out of SQLAlchemy defaults so they are testable and portable (tech.md).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backend.models import Event, Farm, Field, Photo


class ValidationError(ValueError):
    """Raised when an event/photo violates a product rule."""


def _farm_id_for_field(session: Session, field_id: int) -> int:
    farm_id = session.execute(
        select(Field.farm_id).where(Field.id == field_id)
    ).scalar_one_or_none()
    if farm_id is None:
        raise ValidationError(f"field {field_id} does not exist")
    return farm_id


def _next_display_id(session: Session, model, farm_id: int, prefix: str) -> str:
    """Per-farm sequential display id, e.g. E-014 / P-007.

    Counts existing rows for the farm's fields and increments.
    """
    count = session.execute(
        select(func.count())
        .select_from(model)
        .join(Field, model.field_id == Field.id)
        .where(Field.farm_id == farm_id)
    ).scalar_one()
    return f"{prefix}-{count + 1:03d}"


def next_event_display_id(session: Session, field_id: int) -> str:
    farm_id = _farm_id_for_field(session, field_id)
    return _next_display_id(session, Event, farm_id, "E")


def next_photo_display_id(session: Session, field_id: int) -> str:
    farm_id = _farm_id_for_field(session, field_id)
    return _next_display_id(session, Photo, farm_id, "P")


def validate_event_fields(
    *, occurred_at: date, quantity: float | None, today: date | None = None
) -> None:
    """Reject future dates and negative quantities (guide section 5)."""
    today = today or date.today()
    if occurred_at > today:
        raise ValidationError(f"occurred_at {occurred_at} is in the future")
    if quantity is not None and quantity < 0:
        raise ValidationError(f"quantity {quantity} is negative")


def create_event(session: Session, *, field_id: int, today: date | None = None, **kwargs) -> Event:
    """Create an Event with validation + per-farm display id. Does not commit."""
    validate_event_fields(
        occurred_at=kwargs["occurred_at"], quantity=kwargs.get("quantity"), today=today
    )
    display_id = next_event_display_id(session, field_id)
    event = Event(field_id=field_id, display_id=display_id, **kwargs)
    session.add(event)
    session.flush()
    return event