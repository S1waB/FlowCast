"""
FlowCast – Thread-safe in-memory job store.

In production, replace with Redis or a DB-backed queue.
The store is a module-level singleton; all FastAPI workers in the same process
share it safely via a threading.Lock.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas import JobStatus


# ─────────────────────────────────────────────────────────────────────────────
# Job model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BulletinJob:
    """Mutable job record stored in memory."""

    job_id: str
    clip_count: int
    voice_clip_paths: list[str] = field(default_factory=list)

    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    transitions_count: Optional[int] = None
    duration_ms: Optional[int] = None
    output_path: Optional[str] = None
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Store operations
# ─────────────────────────────────────────────────────────────────────────────

_store: dict[str, BulletinJob] = {}
_lock = threading.Lock()


def create_job(voice_clip_paths: list[str | Path]) -> BulletinJob:
    """Create a new job record and add it to the store."""
    paths = [str(p) for p in voice_clip_paths]
    job = BulletinJob(
        job_id=str(uuid.uuid4()),
        clip_count=len(paths),
        voice_clip_paths=paths,
    )
    with _lock:
        _store[job.job_id] = job
    return job


def get_job(job_id: str) -> Optional[BulletinJob]:
    """Return the job, or None if it does not exist."""
    with _lock:
        return _store.get(job_id)


def update_job(job_id: str, **kwargs: object) -> None:
    """
    Update one or more fields on a job record atomically.

    Unknown field names are silently ignored to avoid hard failures on schema
    changes.
    """
    with _lock:
        job = _store.get(job_id)
        if job is None:
            return
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
