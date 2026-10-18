"""Engine unit tests (guide task 3). No AI, no network. Target: 25+ tests."""
from __future__ import annotations

from datetime import date

import pytest

from app.backend.db.service import create_event
from app.backend.models import DateCertainty, EventSource, EventType, Farm, Field, Photo
from harness.engine import (
    Comparison,
    compare_values,
    days_between,
    find_gaps,
    get_timeline,
    normalize_unit,
    resolve_days_ago,
)

TODAY = date(2026, 3, 15)


def _field(session, crop="tomato") -> Field:
    farm = Farm(name="F")
    session.add(farm)
    session.flush()
    fl = Field(farm_id=farm.id, name="N", crop=crop)
    session.add(fl)
    session.flush()
    return fl


def _ev(session, field, type_, occurred, **kw):
    return create_event(
        session, field_id=field.id, type=type_, occurred_at=occurred,
        source=EventSource.farmer_text, today=TODAY, **kw,
    )


# --- days_between -------------------------------------------------------------
def test_days_between_simple():
    assert days_between(date(2026, 3, 1), date(2026, 3, 8)) == 7


def test_days_between_symmetric():
    assert days_between(date(2026, 3, 8), date(2026, 3, 1)) == 7


def test_days_between_same_day():
    assert days_between(TODAY, TODAY) == 0


def test_days_between_across_month():
    assert days_between(date(2026, 2, 25), date(2026, 3, 2)) == 5


def test_days_between_across_year():
    assert days_between(date(2025, 12, 30), date(2026, 1, 2)) == 3


# --- resolve_days_ago ---------------------------------------------------------
def test_resolve_days_ago_zero():
    assert resolve_days_ago(0, TODAY) == TODAY


def test_resolve_days_ago_week():
    assert resolve_days_ago(7, TODAY) == date(2026, 3, 8)


def test_resolve_days_ago_month_boundary():
    assert resolve_days_ago(20, TODAY) == date(2026, 2, 23)


def test_resolve_days_ago_year_boundary():
    assert resolve_days_ago(100, date(2026, 1, 10)) == date(2025, 10, 2)


# --- normalize_unit -----------------------------------------------------------
def test_normalize_bori_to_kg():
    assert normalize_unit(2, "bori") == (100.0, "kg")


def test_normalize_kg_identity():
    assert normalize_unit(10, "kg") == (10.0, "kg")


def test_normalize_grams():
    assert normalize_unit(500, "g") == (0.5, "kg")


def test_normalize_litre():
    assert normalize_unit(5, "litre") == (5.0, "litre")


def test_normalize_tanki():
    assert normalize_unit(1, "tanki") == (200.0, "litre")


def test_normalize_unknown_unit_passthrough():
    assert normalize_unit(3, "widget") == (3, "widget")


def test_normalize_none_quantity():
    assert normalize_unit(None, "kg") == (None, "kg")


def test_normalize_case_insensitive():
    assert normalize_unit(1, "BORI") == (50.0, "kg")


# --- get_timeline -------------------------------------------------------------
def test_timeline_sorted(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 3, 10))
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 5))
    session.commit()
    tl = get_timeline(session, fl.id)
    assert [i.occurred_at for i in tl] == [date(2026, 3, 5), date(2026, 3, 10)]


def test_timeline_empty_window(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 1, 1))
    session.commit()
    tl = get_timeline(session, fl.id, start=date(2026, 3, 1), end=date(2026, 3, 15))
    assert tl == []


def test_timeline_window_bounds_inclusive(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 3, 1))
    _ev(session, fl, EventType.irrigation, date(2026, 3, 15))
    session.commit()
    tl = get_timeline(session, fl.id, start=date(2026, 3, 1), end=date(2026, 3, 15))
    assert len(tl) == 2


def test_timeline_duplicate_events_kept(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 3, 10))
    _ev(session, fl, EventType.irrigation, date(2026, 3, 10))
    session.commit()
    tl = get_timeline(session, fl.id)
    assert len(tl) == 2


# --- find_gaps ----------------------------------------------------------------
def test_gaps_all_missing_on_empty(session):
    fl = _field(session)
    session.commit()
    g = find_gaps(session, fl.id, window_days=14, end=TODAY)
    assert g.missing_irrigation and g.missing_fertilizer and g.missing_weather
    assert g.has_gaps


def test_gaps_irrigation_present(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 3, 10), quantity=5, unit="litre")
    session.commit()
    g = find_gaps(session, fl.id, window_days=14, end=TODAY)
    assert not g.missing_irrigation
    assert g.missing_fertilizer


def test_gaps_null_quantity_flagged(session):
    fl = _field(session)
    e = _ev(session, fl, EventType.fertilizer, date(2026, 3, 10))  # no quantity
    session.commit()
    g = find_gaps(session, fl.id, window_days=14, end=TODAY)
    assert e.display_id in g.null_quantity_events


def test_gaps_unknown_date_flagged(session):
    fl = _field(session)
    e = _ev(session, fl, EventType.irrigation, date(2026, 3, 10), quantity=3, unit="litre",
            date_certainty=DateCertainty.unknown)
    session.commit()
    g = find_gaps(session, fl.id, window_days=14, end=TODAY)
    assert e.display_id in g.unknown_date_events


def test_gaps_window_excludes_old_events(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 2, 1), quantity=3, unit="litre")
    session.commit()
    g = find_gaps(session, fl.id, window_days=14, end=TODAY)
    assert g.missing_irrigation  # old event outside 14-day window


def test_gaps_no_gaps_when_all_present(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 3, 10), quantity=3, unit="litre")
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 11), quantity=1, unit="bori")
    _ev(session, fl, EventType.weather, date(2026, 3, 12))
    session.commit()
    g = find_gaps(session, fl.id, window_days=14, end=TODAY)
    assert not g.has_gaps


# --- compare_values -----------------------------------------------------------
def test_compare_detects_increase(session):
    fl = _field(session)
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 1), product="urea", quantity=1, unit="bori")
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 10), product="urea", quantity=2, unit="bori")
    session.commit()
    comps = compare_values(session, fl.id, EventType.fertilizer)
    assert len(comps) == 1
    assert comps[0].percent_change == 100.0


def test_compare_different_products_not_compared(session):
    fl = _field(session)
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 1), product="urea", quantity=1, unit="bori")
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 10), product="DAP", quantity=2, unit="bori")
    session.commit()
    comps = compare_values(session, fl.id, EventType.fertilizer)
    assert comps == []


def test_compare_unit_normalized_before_comparison(session):
    fl = _field(session)
    # 50 kg then 1 bori (=50 kg) -> no change
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 1), product="urea", quantity=50, unit="kg")
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 10), product="urea", quantity=1, unit="bori")
    session.commit()
    comps = compare_values(session, fl.id, EventType.fertilizer)
    assert comps[0].percent_change == 0.0


def test_compare_null_quantity_skipped(session):
    fl = _field(session)
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 1), product="urea")  # null qty
    _ev(session, fl, EventType.fertilizer, date(2026, 3, 10), product="urea", quantity=2, unit="bori")
    session.commit()
    comps = compare_values(session, fl.id, EventType.fertilizer)
    assert comps == []


def test_compare_conflicting_same_day_records(session):
    fl = _field(session)
    _ev(session, fl, EventType.irrigation, date(2026, 3, 10), product=None, quantity=5, unit="litre")
    _ev(session, fl, EventType.irrigation, date(2026, 3, 10), product=None, quantity=10, unit="litre")
    session.commit()
    comps = compare_values(session, fl.id, EventType.irrigation)
    assert len(comps) == 1
    assert comps[0].percent_change == 100.0


def test_compare_empty(session):
    fl = _field(session)
    session.commit()
    assert compare_values(session, fl.id, EventType.fertilizer) == []