"""Photo endpoints: upload, resize, quality checks, vision observation, confirm (guide section 6 & 9)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.api.photo_utils import process_uploaded_image
from app.backend.db.service import create_event, next_photo_display_id
from app.backend.db.session import get_session
from app.backend.models import DateCertainty, EventSource, EventType, Field, Photo
from harness.providers.factory import first_provider

router = APIRouter(tags=["photos"])


class PhotoUploadResponse(BaseModel):
    id: int
    display_id: str
    field_id: int
    taken_at: str | None
    quality_flags: dict[str, Any]
    verified_by_farmer: bool


class ObservationConfirmRequest(BaseModel):
    observation: dict[str, Any]
    symptom_summary: str | None = None


@router.post("/photos", response_model=PhotoUploadResponse, status_code=201)
async def upload_photo(
    field_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> PhotoUploadResponse:
    """Upload, resize (max 1280px JPEG), EXIF date, quality checks (blur/dark/overexposed)."""
    field_obj = db.get(Field, field_id)
    if not field_obj:
        raise HTTPException(status_code=404, detail="Field not found")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty image file")

    try:
        processed_bytes, taken_at, quality_flags = process_uploaded_image(raw_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Image processing error: {exc}")

    display_id = next_photo_display_id(db, field_id)
    photo = Photo(
        display_id=display_id,
        field_id=field_id,
        taken_at=taken_at,
        data=processed_bytes,
        quality_flags=quality_flags,
        verified_by_farmer=False,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    return PhotoUploadResponse(
        id=photo.id,
        display_id=photo.display_id,
        field_id=photo.field_id,
        taken_at=photo.taken_at.isoformat() if photo.taken_at else None,
        quality_flags=photo.quality_flags or {},
        verified_by_farmer=photo.verified_by_farmer,
    )


@router.get("/photos/{photo_id}/file")
def get_photo_file(
    photo_id: int,
    db: Session = Depends(get_session),
) -> Response:
    photo = db.get(Photo, photo_id)
    if not photo or not photo.data:
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=photo.data, media_type="image/jpeg")


@router.post("/photos/{photo_id}/observe")
def observe_photo(
    photo_id: int,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Vision model returns visible symptoms only. Labelled unconfirmed until farmer verifies."""
    photo = db.get(Photo, photo_id)
    if not photo or not photo.data:
        raise HTTPException(status_code=404, detail="Photo not found")

    vlm = first_provider("vision")
    if not vlm:
        # Graceful fallback: return schema with nulls
        observation = {
            "leaf_color": None,
            "pattern": None,
            "spots": None,
            "wilting": None,
            "affected_area": None,
            "notes": "No vision model backend available for automated observation.",
        }
    else:
        res = vlm.observe(photo.data)
        if not res.ok or res.value is None:
            err_msg = res.error.message if res.error else "Vision observation failed"
            raise HTTPException(status_code=502, detail=f"VLM error: {err_msg}")
        observation = res.value

    photo.vision_observation = observation
    db.commit()
    return {
        "photo_id": photo.id,
        "display_id": photo.display_id,
        "observation": observation,
        "verified_by_farmer": False,
    }


@router.post("/photos/{photo_id}/confirm")
def confirm_photo_observation(
    photo_id: int,
    payload: ObservationConfirmRequest,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Farmer confirms or edits observation and optionally generates an observation event."""
    photo = db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    photo.vision_observation = payload.observation
    photo.verified_by_farmer = True

    # If the observation has symptoms, create a linked photo_observation event
    event_id: str | None = None
    if payload.symptom_summary:
        from datetime import date
        event_date = photo.taken_at.date() if photo.taken_at else date.today()
        event = create_event(
            db,
            field_id=photo.field_id,
            type=EventType.photo_observation,
            occurred_at=event_date,
            date_certainty=DateCertainty.exact if photo.taken_at else DateCertainty.approximate,
            product=None,
            quantity=None,
            unit=None,
            symptom=payload.symptom_summary,
            source=EventSource.vision_model,
            raw_text=f"Confirmed photo observation for {photo.display_id}: {payload.symptom_summary}",
            confidence=0.9,
            verified_by_farmer=True,
        )
        photo.event_id = event.id
        event_id = event.display_id

    db.commit()
    return {
        "status": "ok",
        "photo_id": photo.id,
        "display_id": photo.display_id,
        "verified_by_farmer": True,
        "linked_event_id": event_id,
    }
