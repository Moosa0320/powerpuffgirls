"""SQLAlchemy 2.0 models for FasalNama (guide section 5).

Portability rules (tech.md):
- No SQLite-only SQL. JSON via SQLAlchemy JSON type, binary via LargeBinary.
- Display IDs (E-###, P-###) generated in a service helper, not DB defaults.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EventType(str, enum.Enum):
    planting = "planting"
    irrigation = "irrigation"
    fertilizer = "fertilizer"
    pesticide = "pesticide"
    weather = "weather"
    observation = "observation"
    harvest = "harvest"
    photo_observation = "photo_observation"


class DateCertainty(str, enum.Enum):
    exact = "exact"
    approximate = "approximate"
    unknown = "unknown"


class EventSource(str, enum.Enum):
    farmer_text = "farmer_text"
    farmer_voice = "farmer_voice"
    weather_api = "weather_api"
    vision_model = "vision_model"


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    fields: Mapped[list["Field"]] = relationship(back_populates="farm", cascade="all, delete-orphan")


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    crop: Mapped[str | None] = mapped_column(String(120), nullable=True)
    planting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    area: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    farm: Mapped["Farm"] = relationship(back_populates="fields")
    events: Mapped[list["Event"]] = relationship(back_populates="field", cascade="all, delete-orphan")
    photos: Mapped[list["Photo"]] = relationship(back_populates="field", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # E-014
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), nullable=False, index=True)
    type: Mapped[EventType] = mapped_column(Enum(EventType, native_enum=False), nullable=False)
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False)
    date_certainty: Mapped[DateCertainty] = mapped_column(
        Enum(DateCertainty, native_enum=False), default=DateCertainty.exact, nullable=False
    )
    product: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    symptom: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source: Mapped[EventSource] = mapped_column(Enum(EventSource, native_enum=False), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_by_farmer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    field: Mapped["Field"] = relationship(back_populates="events")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # P-007
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), nullable=False, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quality_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    vision_observation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified_by_farmer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    field: Mapped["Field"] = relationship(back_populates="photos")


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), nullable=False, index=True)
    symptom_date: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verifier_log: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)