"""Open-Meteo historical weather integration (guide section 9).

Fetches rainfall and temperature for field coordinates and creates weather events.
All weather events note that data is area-level, not field-level.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.backend.db.service import create_event
from app.backend.models import DateCertainty, Event, EventSource, EventType, Field


def sync_field_weather(
    session: Session,
    field: Field,
    start_date: date,
    end_date: date,
) -> list[Event]:
    """Pulls Open-Meteo historical rainfall into weather events."""
    if field.latitude is None or field.longitude is None:
        raise ValueError(f"Field {field.name} lacks latitude/longitude coordinates")

    import httpx

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": field.latitude,
        "longitude": field.longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ["precipitation_sum", "temperature_2m_max", "temperature_2m_min"],
        "timezone": "auto",
    }

    try:
        r = httpx.get(url, params=params, timeout=15)
        if r.status_code != 200:
            # Fall back to forecast API with past_days if archive has delay
            forecast_url = "https://api.open-meteo.com/v1/forecast"
            r = httpx.get(
                forecast_url,
                params={
                    "latitude": field.latitude,
                    "longitude": field.longitude,
                    "past_days": max(1, min(14, (end_date - start_date).days)),
                    "daily": ["precipitation_sum", "temperature_2m_max"],
                    "timezone": "auto",
                },
                timeout=15,
            )
        data = r.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        precips = daily.get("precipitation_sum", [])
        t_maxes = daily.get("temperature_2m_max", [])
    except Exception as exc:
        raise RuntimeError(f"Open-Meteo sync failed: {exc}") from exc

    created: list[Event] = []
    # Identify existing weather events in this date range to prevent duplicates
    existing_dates = {
        e.occurred_at
        for e in session.query(Event).filter(
            Event.field_id == field.id,
            Event.type == EventType.weather,
            Event.occurred_at >= start_date,
            Event.occurred_at <= end_date,
        ).all()
    }

    for d_str, precip, t_max in zip(dates, precips, t_maxes):
        try:
            day = date.fromisoformat(d_str)
        except Exception:
            continue
        if day in existing_dates:
            continue
        # Only record notable weather (rain > 0 or recorded daily snapshot)
        rain_val = float(precip) if precip is not None else 0.0
        t_val = float(t_max) if t_max is not None else None

        desc = f"Area rainfall: {rain_val:.1f} mm"
        if t_val is not None:
            desc += f", max temp: {t_val:.1f}°C"
        desc += " (Open-Meteo area-level data, not field-level)"

        event = create_event(
            session,
            field_id=field.id,
            type=EventType.weather,
            occurred_at=day,
            date_certainty=DateCertainty.exact,
            product="rainfall",
            quantity=rain_val,
            unit="mm",
            source=EventSource.weather_api,
            raw_text=desc,
            confidence=0.95,
            verified_by_farmer=True,
        )
        created.append(event)

    session.commit()
    return created
