"""Event endpoints: transcribe, parse, confirm, and timeline (guide section 6)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend.db.service import create_event
from app.backend.db.session import get_session
from app.backend.models import DateCertainty, Event, EventSource, EventType, Field
from harness import engine
from harness.parser import ProposedEvent, parse_text
from harness.providers.factory import first_provider

router = APIRouter(tags=["events"])


class ParseRequest(BaseModel):
    field_id: int
    text: str


class ParseResponse(BaseModel):
    events: list[ProposedEvent]
    error: str | None = None
    attempts: int = 1


class ConfirmEventItem(BaseModel):
    type: str
    occurred_at: date
    date_certainty: Literal["exact", "approximate", "unknown"] = "exact"
    product: str | None = None
    quantity: float | None = None
    unit: str | None = None
    symptom: str | None = None
    source: str = "farmer_text"
    raw_text: str | None = None
    confidence: float | None = 1.0


class ConfirmRequest(BaseModel):
    field_id: int
    events: list[ConfirmEventItem]


class TranscribeResponse(BaseModel):
    transcript: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
) -> TranscribeResponse:
    """Audio upload (max 30s) -> returns transcript only (guide section 6 & 9)."""
    stt = first_provider("stt")
    if not stt:
        raise HTTPException(
            status_code=503,
            detail="No STT backend available. Please use typed input.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file")

    initial_prompt = "urea, DAP, tomato, tamatar, pani, spray, khad, bori, tanki, patta peela"
    res = stt.transcribe(content, language="ur", initial_prompt=initial_prompt)
    if not res.ok or not res.value:
        err_msg = res.error.message if res.error else "Transcription failed"
        raise HTTPException(status_code=502, detail=f"STT error: {err_msg}")

    return TranscribeResponse(transcript=res.value)


@router.post("/parse", response_model=ParseResponse)
def parse_farmer_note(
    payload: ParseRequest,
    db: Session = Depends(get_session),
) -> ParseResponse:
    """Text plus field_id returns proposed events (not saved)."""
    field_obj = db.get(Field, payload.field_id)
    if not field_obj:
        raise HTTPException(status_code=404, detail="Field not found")

    text = payload.text.strip()
    if not text:
        return ParseResponse(events=[], error=None)

    llm = first_provider("llm")
    if not llm:
        raise HTTPException(
            status_code=503,
            detail="No LLM backend available for parsing.",
        )

    # Collect other field names on same farm for context
    fields_on_farm = db.execute(
        select(Field.name).where(Field.farm_id == field_obj.farm_id)
    ).scalars().all()

    result = parse_text(
        text=text,
        today=date.today(),
        llm=llm,
        source="farmer_text",
        field_names=list(fields_on_farm),
    )

    if result.error and not result.events:
        raise HTTPException(status_code=502, detail=result.error)

    return ParseResponse(
        events=result.events,
        error=result.error,
        attempts=result.attempts,
    )


@router.post("/events/confirm", status_code=201)
def confirm_events(
    payload: ConfirmRequest,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Farmer-edited events saved with verified_by_farmer = true."""
    field_obj = db.get(Field, payload.field_id)
    if not field_obj:
        raise HTTPException(status_code=404, detail="Field not found")

    saved_ids: list[str] = []
    for item in payload.events:
        try:
            etype = EventType(item.type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {item.type}")

        try:
            certainty = DateCertainty(item.date_certainty)
        except ValueError:
            certainty = DateCertainty.exact

        try:
            source = EventSource(item.source)
        except ValueError:
            source = EventSource.farmer_text

        event = create_event(
            db,
            field_id=payload.field_id,
            type=etype,
            occurred_at=item.occurred_at,
            date_certainty=certainty,
            product=item.product,
            quantity=item.quantity,
            unit=item.unit,
            symptom=item.symptom,
            source=source,
            raw_text=item.raw_text,
            confidence=item.confidence or 1.0,
            verified_by_farmer=True,
        )
        saved_ids.append(event.display_id)

    db.commit()
    return {"status": "ok", "saved_count": len(saved_ids), "event_ids": saved_ids}


@router.get("/fields/{field_id}/timeline")
def get_field_timeline(
    field_id: int,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Sorted events and photos for the timeline view."""
    field_obj = db.get(Field, field_id)
    if not field_obj:
        raise HTTPException(status_code=404, detail="Field not found")

    start_date = start or (date.today() - engine.timedelta(days=30))
    end_date = end or date.today()

    items = engine.get_timeline(db, field_id, start_date, end_date)
    return [asdict(i) for i in items]
