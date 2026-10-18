"""DB layer tests (guide task 2)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.backend.db.service import (
    ValidationError,
    create_event,
    next_event_display_id,
    next_photo_display_id,
    validate_event_fields,
)
from app.backend.models import (
    DateCertainty,
    Event,
    EventSource,
    EventType,
    Farm,
    Field,
    Photo,
)


def _make_field(session, name="North") -> Field:
    farm = Farm(name="Test Farm")
    session.add(farm)
    session.flush()
    field = Field(farm_id=farm.id, name=name, crop="tomato")
    session.add(field)
    session.flush()
    return field


def test_create_core_rows(session) -> None:
    field = _make_field(session)
    assert field.id is not None
    assert field.farm_id is not None


def test_event_display_id_sequence_per_farm(session) -> None:
    field = _make_field(session)
    e1 = create_event(
        session, field_id=field.id, type=EventType.irrigation,
        occurred_at=date.today(), source=EventSource.farmer_text,
    )
    e2 = create_event(
        session, field_id=field.id, type=EventType.fertilizer,
        occurred_at=date.today(), source=EventSource.farmer_text,
    )
    assert e1.display_id == "E-001"
    assert e2.display_id == "E-002"


def test_display_ids_scoped_to_farm(session) -> None:
    f1 = _make_field(session, "A")
    create_event(session, field_id=f1.id, type=EventType.irrigation,
                 occurred_at=date.today(), source=EventSource.farmer_text)
    # second farm starts its own sequence
    farm2 = Farm(name="Farm 2")
    session.add(farm2)
    session.flush()
    f2 = Field(farm_id=farm2.id, name="B", crop="wheat")
    session.add(f2)
    session.flush()
    e = create_event(session, field_id=f2.id, type=EventType.irrigation,
                     occurred_at=date.today(), source=EventSource.farmer_text)
    assert e.display_id == "E-001"


def test_photo_display_id(session) -> None:
    field = _make_field(session)
    did = next_photo_display_id(session, field.id)
    assert did == "P-001"


def test_reject_future_date() -> None:
    with pytest.raises(ValidationError):
        validate_event_fields(occurred_at=date.today() + timedelta(days=1), quantity=1.0)


def test_reject_negative_quantity() -> None:
    with pytest.raises(ValidationError):
        validate_event_fields(occurred_at=date.today(), quantity=-5.0)


def test_null_quantity_allowed() -> None:
    validate_event_fields(occurred_at=date.today(), quantity=None)  # no raise


def test_create_event_rejects_future(session) -> None:
    field = _make_field(session)
    with pytest.raises(ValidationError):
        create_event(session, field_id=field.id, type=EventType.irrigation,
                     occurred_at=date.today() + timedelta(days=2),
                     source=EventSource.farmer_text)


def test_enum_values_persist(session) -> None:
    field = _make_field(session)
    ev = create_event(session, field_id=field.id, type=EventType.pesticide,
                      occurred_at=date.today(), source=EventSource.farmer_voice,
                      date_certainty=DateCertainty.approximate)
    session.commit()
    fetched = session.get(Event, ev.id)
    assert fetched.type == EventType.pesticide
    assert fetched.date_certainty == DateCertainty.approximate
    assert fetched.source == EventSource.farmer_voice


def test_photo_json_fields(session) -> None:
    field = _make_field(session)
    photo = Photo(field_id=field.id, display_id="P-001",
                  quality_flags={"blur": False}, vision_observation=None)
    session.add(photo)
    session.commit()
    fetched = session.get(Photo, photo.id)
    assert fetched.quality_flags == {"blur": False}