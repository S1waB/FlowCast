"""
FlowCast – FastAPI application entry point.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

# ── Routers (both root and /api prefixes) ─────────────────────────────────────
app.include_router(health.router)
app.include_router(source_bank.router)
app.include_router(bulletins.router)

app.include_router(health.router, prefix="/api")
app.include_router(source_bank.router, prefix="/api")
app.include_router(bulletins.router, prefix="/api")

# ── Static Frontend ──────────────────────────────────────────────────────────
# Look for 'static' directory in backend, current dir, or 'frontend/dist'
static_dir = Path(__file__).parent.parent / "static"
if not static_dir.exists() and os.path.exists("static"):
    static_dir = Path("static")
if not static_dir.exists():
    candidate_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if candidate_dist.exists():
        static_dir = candidate_dist

if static_dir.exists():
    # Mount assets
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Serve index.html for all other routes to support SPA
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        target_path = static_dir / full_path
        if target_path.is_file():
            return FileResponse(target_path)
        return FileResponse(static_dir / "index.html")
