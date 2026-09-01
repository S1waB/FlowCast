"""Health check router."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


@router.get("", response_model=HealthResponse, summary="Health check")
async def health_check() -> HealthResponse:
    """
    Returns a 200 OK with basic service metadata.

    Use this endpoint for liveness probes (Docker, Kubernetes, load-balancer, etc.).
    """
    from app.core.config import settings  # local import avoids circular deps

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )
