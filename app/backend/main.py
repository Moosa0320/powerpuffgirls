"""FastAPI application for FasalNama (guide section 6).

- Schema: Alembic owns it. Startup upgrades a local SQLite file to head and runs no DDL on
  hosted Postgres, where `alembic upgrade head` runs before deploy.
- Passcode: when APP_PASSCODE is set, every route except /health and the docs needs the
  X-Passcode header. Unset or blank leaves the API open for local dev.
- CORS: origins from CORS_ORIGINS (comma-separated), the Vite dev server when unset.
"""
from __future__ import annotations

import hmac
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.backend.api.events import router as events_router
from app.backend.api.farms import router as farms_router
from app.backend.api.investigations import router as investigations_router
from app.backend.api.photos import router as photos_router
from app.backend.db.session import get_database_url

if TYPE_CHECKING:
    from alembic.config import Config

logger = logging.getLogger("fasalnama.api")

# tests/conftest.py sets this before anything imports the app, so a developer's real .env (API
# keys) never reaches the test process. uvicorn and Vercel runs still load .env.
SKIP_DOTENV_ENV = "FASALNAMA_SKIP_DOTENV"


def load_env_file() -> bool:
    """Load .env unless FASALNAMA_SKIP_DOTENV=1. Returns whether .env loading ran."""
    if os.getenv(SKIP_DOTENV_ENV) == "1":
        return False
    load_dotenv()
    return True


DOTENV_LOADED = load_env_file()

BACKEND_DIR = Path(__file__).resolve().parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

PASSCODE_HEADER = "X-Passcode"
# Liveness and the API docs stay open. Exact paths, so a new /health-something is protected.
OPEN_PATHS = frozenset({"/health", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"})
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)  # Vite dev server


def alembic_config(database_url: str) -> Config:
    """Alembic config for in-process commands, independent of the working directory.

    The ini is loaded by absolute path (script_location uses %(here)s). The URL travels in
    config.attributes, and env.py leaves the caller's logging alone.
    """
    from alembic.config import Config  # lazy: Postgres startup never needs Alembic

    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


def prepare_database(database_url: str | None = None) -> bool:
    """Startup schema step. Returns True when Alembic ran.

    SQLite (local): upgrade to head, a no-op when the file is already current. Anything else
    (hosted Postgres): no DDL and no connection here; migrations run before deploy.
    """
    url = database_url or get_database_url()
    if not url.startswith("sqlite"):
        # Only the scheme is logged: the URL can hold a password.
        logger.info("startup: %s database, no DDL; run `alembic upgrade head` before deploy",
                    url.split(":", 1)[0])
        return False
    from alembic import command  # lazy: about 0.2 s of imports a serverless cold start skips

    command.upgrade(alembic_config(url), "head")
    return True


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    prepare_database()
    yield


class PasscodeMiddleware:
    """401 unless X-Passcode matches APP_PASSCODE, for every route outside OPEN_PATHS.

    APP_PASSCODE is read per request. CORS preflights pass: browsers never send custom
    headers on them. Installed inside CORSMiddleware, so a 401 still carries CORS headers
    for allowed origins and the browser can read it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not passcode_ok(scope):
            response = JSONResponse(
                {"detail": f"Missing or invalid {PASSCODE_HEADER} header"}, status_code=401
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def passcode_ok(scope: Scope) -> bool:
    expected = os.getenv("APP_PASSCODE", "").strip()
    if not expected or scope["path"] in OPEN_PATHS:
        return True
    headers = {name.lower(): value for name, value in scope["headers"]}
    if scope["method"] == "OPTIONS" and b"access-control-request-method" in headers:
        return True  # CORS preflight
    provided = headers.get(PASSCODE_HEADER.lower().encode(), b"").strip()
    return hmac.compare_digest(provided, expected.encode("utf-8"))


def cors_origins(raw: str | None = None) -> list[str]:
    """Allowed browser origins: CORS_ORIGINS split on commas, else the Vite dev server."""
    value = os.getenv("CORS_ORIGINS", "") if raw is None else raw
    origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness for the cloud host and demo warm-up. Open even when APP_PASSCODE is set."""
    run_mode = os.getenv("RUN_MODE", "local")
    return {
        "status": "healthy",
        "service": "FasalNama-api",
        "run_mode": run_mode,
        "llm_backend": os.getenv("LLM_BACKEND", "ollama"),
        "stt_backend": os.getenv("STT_BACKEND", "local"),
        "vision_backend": os.getenv("VISION_BACKEND", "local"),
    }


def create_app() -> FastAPI:
    """Build the API. CORS_ORIGINS is read here; APP_PASSCODE on every request."""
    application = FastAPI(
        title="FasalNama API",
        description="Farm record investigator API built on open-weight AI.",
        version="1.0.0",
        lifespan=lifespan,
    )
    # The middleware added last runs first: CORS wraps the passcode check.
    application.add_middleware(PasscodeMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=False,  # header auth, no cookies
        allow_methods=["GET", "POST"],
        allow_headers=[PASSCODE_HEADER, "Content-Type"],
    )
    for router in (health_router, farms_router, events_router, photos_router,
                   investigations_router):
        application.include_router(router)
    return application


app = create_app()
