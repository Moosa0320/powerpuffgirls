"""FastAPI application for FasalNama (guide section 6)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.backend.api.events import router as events_router
from app.backend.api.farms import router as farms_router
from app.backend.api.investigations import router as investigations_router
from app.backend.api.photos import router as photos_router
from app.backend.db.session import make_engine
from app.backend.models import Base

# Load .env file at startup
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables are created on SQLite locally
    engine = make_engine()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="FasalNama API",
    description="Farm record investigator API built on open-weight AI.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
raw_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def passcode_protection_middleware(request: Request, call_next):
    """Enforces X-Passcode on write and AI endpoints when APP_PASSCODE is configured (section 6)."""
    app_passcode = os.getenv("APP_PASSCODE", "").strip()

    # If no passcode configured, permit all
    if not app_passcode:
        return await call_next(request)

    path = request.url.path
    method = request.method

    # Exempt public read-only and liveness paths
    exempt_prefixes = [
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]
    if any(path.startswith(p) for p in exempt_prefixes):
        return await call_next(request)

    # Permit safe GET requests to public resources
    if method == "GET" and (
        path.startswith("/farms")
        or path.startswith("/fields")
        or "/photos/" in path and path.endswith("/file")
        or "/investigations/" in path and path.endswith("/pdf")
    ):
        return await call_next(request)

    # Check X-Passcode header
    provided_passcode = request.headers.get("X-Passcode", "").strip()
    if provided_passcode != app_passcode:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Unauthorized: Invalid or missing X-Passcode header"},
        )

    return await call_next(request)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness check for Render and demo warmup."""
    run_mode = os.getenv("RUN_MODE", "local")
    return {
        "status": "healthy",
        "service": "FasalNama-api",
        "run_mode": run_mode,
        "llm_backend": os.getenv("LLM_BACKEND", "ollama"),
        "stt_backend": os.getenv("STT_BACKEND", "local"),
        "vision_backend": os.getenv("VISION_BACKEND", "local"),
    }


# Register all feature routers
app.include_router(farms_router)
app.include_router(events_router)
app.include_router(photos_router)
app.include_router(investigations_router)
