"""
FlowCast – Pydantic schemas (request & response bodies).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Source-bank
# ─────────────────────────────────────────────────────────────────────────────

# Only 3 swappable assets — no "transition" asset per spec
VALID_ROLES: frozenset[str] = frozenset({"intro", "outro", "fond"})

# Duration bounds (ms) considered "reasonable" for intro/outro
INTRO_OUTRO_MIN_MS: int = 4_000
INTRO_OUTRO_MAX_MS: int = 10_000


class AssetMetadata(BaseModel):
    """Per-role asset information returned by GET /source-bank."""

    role: str
    path: str
    exists: bool
    size_bytes: Optional[int] = None
    duration_ms: Optional[int] = None
    duration_s: Optional[float] = None
    duration_warning: Optional[str] = None
    """Present when intro/outro duration is outside the 4–10 s recommended range."""


class SourceBankDefaults(BaseModel):
    """Mirror of the mixing parameters in source_bank.json."""

    duck_db: float
    transition_high_db: float
    transition_total_ms: int
    transition_fade_in_ms: int
    transition_fade_out_ms: int
    silence_thresh_db_relative: float
    min_silence_len_ms: int
    segment_trim_pad_ms: int


class SourceBankResponse(BaseModel):
    """Full response for GET /source-bank."""

    roles: dict[str, AssetMetadata]
    defaults: SourceBankDefaults


class AssetUploadResponse(BaseModel):
    """Response for POST /source-bank/{role}."""

    role: str
    path: str
    size_bytes: int
    duration_ms: int
    duration_s: float
    duration_warning: Optional[str] = None
    message: str


class ConfigPatchRequest(BaseModel):
    """
    Partial update for PATCH /source-bank/config.

    All fields are optional; only provided fields are modified.
    """

    duck_db: Optional[float] = Field(
        None,
        ge=-60.0,
        le=0.0,
        description="Background music ducking level in dB (must be ≤ 0).",
    )
    transition_high_db: Optional[float] = Field(
        None,
        ge=-40.0,
        le=0.0,
        description="Peak fond volume during transition in dB.",
    )
    transition_total_ms: Optional[int] = Field(
        None, ge=500, le=30_000, description="Fixed transition duration in ms (default 3000)."
    )
    fade_in_ms: Optional[int] = Field(
        None, ge=0, le=5_000, description="Transition fade-in duration in ms."
    )
    fade_out_ms: Optional[int] = Field(
        None, ge=0, le=5_000, description="Transition fade-out duration in ms."
    )
    silence_thresh_db: Optional[float] = Field(
        None,
        ge=-60.0,
        le=-1.0,
        description="Silence threshold relative to clip mean dBFS (must be negative).",
    )
    min_silence_len_ms: Optional[int] = Field(
        None, ge=50, le=10_000, description="Minimum silence length in ms."
    )
    segment_trim_pad_ms: Optional[int] = Field(
        None, ge=0, le=1_000, description="Safety pad kept on each edge when trimming segments."
    )


class ConfigPatchResponse(BaseModel):
    """Response for PATCH /source-bank/config."""

    message: str
    defaults: SourceBankDefaults


# ─────────────────────────────────────────────────────────────────────────────
# Bulletins / jobs
# ─────────────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class BulletinCreateResponse(BaseModel):
    """Immediate response for POST /bulletins (job accepted)."""

    job_id: str
    status: JobStatus
    message: str


class BulletinStatusResponse(BaseModel):
    """Response for GET /bulletins/{job_id}."""

    job_id: str
    status: JobStatus
    created_at: str
    """ISO-8601 UTC timestamp."""
    segments_count: Optional[int] = None
    """Number of speech segments detected (available once done)."""
    transitions_count: Optional[int] = None
    """Number of transitions inserted = segments_count - 1 (available once done)."""
    duration_ms: Optional[int] = None
    """Final bulletin duration in ms (available once done)."""
    duration_s: Optional[float] = None
    error: Optional[str] = None
    """Human-readable error message (available when status == error)."""
