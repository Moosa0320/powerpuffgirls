"""Farm and Field CRUD endpoints (guide section 6)."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend.db.session import get_session
from app.backend.models import Farm, Field

router = APIRouter(tags=["farms"])


class FarmCreate(BaseModel):
    name: str


class FarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_at: Any


class FieldCreate(BaseModel):
    farm_id: int
    name: str
    crop: str | None = None
    planting_date: date | None = None
    area: float | None = None
    latitude: float | None = None
    longitude: float | None = None


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    farm_id: int
    name: str
    crop: str | None
    planting_date: date | None
    area: float | None
    latitude: float | None
    longitude: float | None


@router.post("/farms", response_model=FarmOut, status_code=201)
def create_farm(payload: FarmCreate, db: Session = Depends(get_session)) -> Farm:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Farm name cannot be empty")
    farm = Farm(name=name)
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


@router.get("/farms", response_model=list[FarmOut])
def list_farms(db: Session = Depends(get_session)) -> list[Farm]:
    return list(db.execute(select(Farm).order_by(Farm.created_at.desc())).scalars().all())


@router.post("/fields", response_model=FieldOut, status_code=201)
def create_field(payload: FieldCreate, db: Session = Depends(get_session)) -> Field:
    farm = db.get(Farm, payload.farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Field name cannot be empty")

    field_obj = Field(
        farm_id=payload.farm_id,
        name=name,
        crop=payload.crop.strip() if payload.crop else None,
        planting_date=payload.planting_date,
        area=payload.area,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(field_obj)
    db.commit()
    db.refresh(field_obj)
    return field_obj


@router.get("/fields", response_model=list[FieldOut])
def list_fields(
    farm_id: int | None = Query(default=None),
    db: Session = Depends(get_session),
) -> list[Field]:
    stmt = select(Field)
    if farm_id is not None:
        stmt = stmt.where(Field.farm_id == farm_id)
    stmt = stmt.order_by(Field.id.asc())
    return list(db.execute(stmt).scalars().all())
