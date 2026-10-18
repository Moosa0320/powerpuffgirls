"""Investigation, Weather sync, PDF download and Speech API endpoints (guide section 6)."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.api.pdf_generator import generate_expert_handoff_pdf
from app.backend.api.weather_sync import sync_field_weather
from app.backend.db.session import get_session
from app.backend.models import Farm, Field, Investigation
from harness.investigator import Investigator
from harness.providers.factory import first_provider

router = APIRouter(tags=["investigations"])


class WeatherSyncRequest(BaseModel):
    field_id: int
    start_date: date | None = None
    end_date: date | None = None


class InvestigateRequest(BaseModel):
    field_id: int
    symptom_date: date
    window_days: int = 14
    lang: Literal["en", "ur", "roman"] = "en"


class SpeakRequest(BaseModel):
    text: str
    lang: str = "ur"


@router.post("/weather/sync")
def sync_weather_for_field(
    payload: WeatherSyncRequest,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Pull Open-Meteo historical weather into field events."""
    field_obj = db.get(Field, payload.field_id)
    if not field_obj:
        raise HTTPException(status_code=404, detail="Field not found")

    end = payload.end_date or date.today()
    start = payload.start_date or (end - date.resolution * 14)

    try:
        events = sync_field_weather(db, field_obj, start, end)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Weather sync error: {exc}")

    return {
        "status": "ok",
        "synced_count": len(events),
        "event_ids": [e.display_id for e in events],
    }


@router.post("/investigate")
def run_investigation(
    payload: InvestigateRequest,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Runs harness investigator loop with progressive disclosure and verifier."""
    field_obj = db.get(Field, payload.field_id)
    if not field_obj:
        raise HTTPException(status_code=404, detail="Field not found")

    llm = first_provider("llm")
    investigator = Investigator(db, llm)

    outcome = investigator.run(
        field_id=payload.field_id,
        symptom_date=payload.symptom_date,
        window_days=payload.window_days,
        lang=payload.lang,
    )

    inv_record = Investigation(
        field_id=payload.field_id,
        symptom_date=payload.symptom_date,
        window_days=payload.window_days,
        report_json=outcome.report,
        verifier_log={"entries": outcome.verifier_log},
        used_fallback=outcome.used_fallback,
        model_info=outcome.model_info,
    )
    db.add(inv_record)
    db.commit()
    db.refresh(inv_record)

    return {
        "investigation_id": inv_record.id,
        "field_id": payload.field_id,
        "symptom_date": payload.symptom_date.isoformat(),
        "window_days": payload.window_days,
        "used_fallback": outcome.used_fallback,
        "report": outcome.report,
        "verifier_log": outcome.verifier_log,
        "model_info": outcome.model_info,
        "steps": outcome.steps,
    }


@router.get("/investigations/{investigation_id}")
def get_investigation(
    investigation_id: int,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    record = db.get(Investigation, investigation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Investigation not found")

    return {
        "id": record.id,
        "field_id": record.field_id,
        "symptom_date": record.symptom_date.isoformat(),
        "window_days": record.window_days,
        "used_fallback": record.used_fallback,
        "report": record.report_json,
        "verifier_log": record.verifier_log,
        "model_info": record.model_info,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/investigations/{investigation_id}/pdf")
def get_investigation_pdf(
    investigation_id: int,
    db: Session = Depends(get_session),
) -> Response:
    """Returns a one-page expert handoff PDF."""
    record = db.get(Investigation, investigation_id)
    if not record or not record.report_json:
        raise HTTPException(status_code=404, detail="Investigation report not found")

    field_obj = db.get(Field, record.field_id)
    farm_name = "Farm"
    field_name = "Field"
    crop = None
    if field_obj:
        field_name = field_obj.name
        crop = field_obj.crop
        farm = db.get(Farm, field_obj.farm_id)
        if farm:
            farm_name = farm.name

    pdf_bytes = generate_expert_handoff_pdf(
        investigation_id=record.id,
        farm_name=farm_name,
        field_name=field_name,
        crop=crop,
        symptom_date=record.symptom_date.isoformat(),
        window_days=record.window_days,
        report=record.report_json,
    )

    filename = f"FasalNama_Handoff_INV{record.id:03d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/speak")
def speak_report_text(
    payload: SpeakRequest,
) -> Response:
    """Report text to audio (Piper, ElevenLabs, or 501 if none configured)."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text to speak")

    tts = first_provider("tts")
    if not tts:
        raise HTTPException(
            status_code=501,
            detail="No TTS backend configured. Use browser speech synthesis.",
        )

    res = tts.speak(text, lang=payload.lang)
    if not res.ok or not res.value:
        err_msg = res.error.message if res.error else "TTS failed"
        raise HTTPException(status_code=502, detail=f"TTS error: {err_msg}")

    return Response(content=res.value, media_type="audio/mpeg")
