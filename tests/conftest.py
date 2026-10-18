"""Shared fixtures. DB URL comes from TEST_DATABASE_URL (default in-memory SQLite),
so the same suite runs on SQLite and Postgres in CI (guide task 2 acceptance)."""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.backend.db.session import make_engine, make_session_factory
from app.backend.models import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    url = os.getenv("TEST_DATABASE_URL", "sqlite://")  # in-memory
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()