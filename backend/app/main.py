"""
FlowCast – FastAPI application entry point.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import bulletins, health, source_bank


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ensure runtime directories exist on startup."""
    for directory in (
        settings.source_bank_dir,
        settings.uploads_dir,
        settings.output_dir,
        settings.config_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    yield  # application is running
    # (add shutdown logic here if needed)


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "FlowCast: automatic audio news bulletin mixer. "
        "Combines raw vocal clips with intro, outro, background music "
        "and transition sounds using pydub + ffmpeg."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (relaxed for local dev) ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(source_bank.router)
app.include_router(bulletins.router)
