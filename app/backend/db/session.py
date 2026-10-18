"""Database engine and session factory driven by DATABASE_URL.

Same code runs on sqlite:/// locally and postgresql+psycopg:// on Render.
No SQLite-only SQL anywhere (tech.md hard rule).
"""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "sqlite:///./fasalnama.db"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_URL)


def make_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        # Needed only for SQLite's single-thread default; harmless portability shim.
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, future=True)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    engine = engine or make_engine()
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


# Default app-wide factory (lazy).
_SessionFactory: sessionmaker[Session] | None = None


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = make_session_factory()
    return _SessionFactory


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()