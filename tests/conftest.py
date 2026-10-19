"""Shared fixtures. DB URL comes from TEST_DATABASE_URL (default in-memory SQLite),
so the same suite runs on SQLite and Postgres in CI (guide task 2 acceptance).

No .env in tests: FASALNAMA_SKIP_DOTENV=1 is set below, before pytest imports any test module,
and app.backend.main skips load_dotenv when it sees it.

No network: the autouse `network_guard` fails any test whose code reaches a real httpx
transport. Stub the call instead (monkeypatch httpx.post or httpx.get, or httpx.MockTransport).

API tests (tasks 11.2-11.4) take the `api` fixture, an ApiHarness:

    def test_parse(api: ApiHarness) -> None:
        field = Field(name="North", crop="tomato", farm=Farm(name="Demo"))
        api.seed(field)
        api.use_providers(llm=FakeLLM([reply_json]))
        r = api.client.post("/parse", json={"field_id": field.id, "text": "kal pani diya"})

- api.client is a TestClient over a fresh temp-file SQLite DB, created by the real startup
  (Alembic upgrade to head). get_session is overridden through app.dependency_overrides and the
  lazy app-wide session factory points at the same file, so ./fasalnama.db is never touched.
- api.seed(*rows) commits ORM rows (ids stay readable); api.session_factory() opens a session
  for asserts.
- Secret and provider env vars (GROQ_*, HF_*, ELEVENLABS_*, *_BACKEND, APP_PASSCODE,
  CORS_ORIGINS) are removed. Set what a test needs with monkeypatch.setenv: APP_PASSCODE is read
  per request, CORS_ORIGINS only when main.create_app() runs.
- Providers: the API modules import first_provider from harness.providers.factory by name, so
  patching the factory module alone changes nothing for them. The fixture patches first_provider
  and build_chain in every loaded app.* and harness.* module that holds them. Every kind starts
  with no backend (the routes' 503/501 paths). api.use_providers(llm=FakeLLM([...]),
  stt=[failing, working]) injects fakes from harness.providers.fakes; a list is a fallback chain.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy.orm import Session

from app.backend.db.session import make_engine, make_session_factory
from app.backend.models import Base

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import sessionmaker

    from harness.providers.base import Provider

# Read by app.backend.main at import. Test modules are imported after this file, so the real
# .env (API keys) never reaches the test process.
os.environ["FASALNAMA_SKIP_DOTENV"] = "1"

SCRUBBED_ENV_PREFIXES = ("GROQ_", "HF_", "ELEVENLABS_")
SCRUBBED_ENV_SUFFIXES = ("_BACKEND",)
SCRUBBED_ENV_NAMES = frozenset({"APP_PASSCODE", "CORS_ORIGINS", "HUGGING_FACE_HUB_TOKEN"})


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


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Block real httpx transports and fail the test at teardown if code reached one.

    Providers turn the ConnectError into a typed result, so the teardown check is what catches
    it. Stubs (patched httpx.post/get, MockTransport) and TestClient never get here. Yields the
    list of blocked "METHOD host" attempts.
    """
    attempts: list[str] = []

    def blocked(_transport: object, request: httpx.Request) -> httpx.Response:
        attempts.append(f"{request.method} {request.url.host}")
        raise httpx.ConnectError("network disabled in tests", request=request)

    async def blocked_async(_transport: object, request: httpx.Request) -> httpx.Response:
        return blocked(_transport, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked_async)
    yield attempts
    assert not attempts, f"test reached the network through httpx without a stub: {attempts}"


@dataclass
class ApiHarness:
    """What the `api` fixture yields. See the module docstring for usage."""

    client: TestClient
    app: FastAPI
    engine: Engine
    session_factory: sessionmaker[Session]
    database_url: str
    providers: dict[str, Provider | list[Provider]]

    def seed(self, *rows: object) -> None:
        """Insert ORM rows in one committed transaction."""
        with self.session_factory() as db:
            db.add_all(rows)
            db.commit()

    def use_providers(self, **providers: Provider | list[Provider] | None) -> None:
        """first_provider(kind) / build_chain(kind) return these in every API module.

        Kinds: stt, llm, vision, tts. A list is a fallback chain; None means no backend.
        """
        from harness.providers.factory import ENV_KEYS

        unknown = set(providers) - set(ENV_KEYS)
        if unknown:
            raise ValueError(f"unknown provider kinds: {sorted(unknown)}")
        for kind, value in providers.items():
            if value is None:
                self.providers.pop(kind, None)
            else:
                self.providers[kind] = value


def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        upper = name.upper()
        if (upper.startswith(SCRUBBED_ENV_PREFIXES) or upper.endswith(SCRUBBED_ENV_SUFFIXES)
                or upper in SCRUBBED_ENV_NAMES):
            monkeypatch.delenv(name, raising=False)


def _patch_providers(
    monkeypatch: pytest.MonkeyPatch, providers: dict[str, Provider | list[Provider]]
) -> None:
    """Swap first_provider and build_chain wherever app/harness modules imported them."""
    from harness.providers import factory

    def chain(kind: str) -> list[Provider]:
        if kind not in factory.ENV_KEYS:
            raise ValueError(f"unknown provider kind: {kind}")
        value = providers.get(kind)
        if value is None:
            return []
        return list(value) if isinstance(value, list) else [value]

    def fake_build_chain(kind: str, env: Any = None, registry: Any = None) -> list[Provider]:
        return chain(kind)

    def fake_first_provider(kind: str, env: Any = None) -> Provider | None:
        found = chain(kind)
        return found[0] if found else None

    swaps = {
        "first_provider": (factory.first_provider, fake_first_provider),
        "build_chain": (factory.build_chain, fake_build_chain),
    }
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith(("app.", "harness.")):
            continue
        for attr, (original, fake) in swaps.items():
            if getattr(module, attr, None) is original:
                monkeypatch.setattr(module, attr, fake)


@pytest.fixture()
def api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[ApiHarness]:
    """TestClient over a fresh temp-file SQLite DB with fake-only providers (see module docs)."""
    from fastapi.testclient import TestClient

    from app.backend.db import session as db_session
    from app.backend.main import create_app

    _scrub_env(monkeypatch)
    url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    factory = make_session_factory(engine)
    monkeypatch.setattr(db_session, "_SessionFactory", factory)  # callers outside Depends too
    providers: dict[str, Provider | list[Provider]] = {}
    _patch_providers(monkeypatch, providers)

    def override_get_session() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[db_session.get_session] = override_get_session
    try:
        with TestClient(app) as client:  # runs startup: Alembic upgrade to head on the file
            yield ApiHarness(client=client, app=app, engine=engine, session_factory=factory,
                             database_url=url, providers=providers)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
