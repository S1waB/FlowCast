"""
conftest.py – shared fixtures for FlowCast audio engine tests.

All audio is synthesised in memory; no real MP3 files needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

# ── Make sure `app/` is importable when pytest is run from backend/ ──────────
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Audio-generation helpers ─────────────────────────────────────────────────

SPEECH_VOLUME_DB: float = -6.0
"""Loud enough to be unambiguously above any silence threshold used in tests."""

TRANSITION_VOLUME_DB: float = -20.0
"""Quiet transition asset – it's overlaid, not mixed for loudness."""

BED_VOLUME_DB: float = -20.0


def sine_tone(freq: int, duration_ms: int, volume_db: float) -> AudioSegment:
    """Return a mono sine-wave AudioSegment at *volume_db* dBFS."""
    return Sine(freq).to_audio_segment(duration=duration_ms, volume=volume_db)


# ── Reusable fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def speech() -> AudioSegment:
    """2 000 ms of clear speech-like tone."""
    return sine_tone(440, 2_000, SPEECH_VOLUME_DB)


@pytest.fixture
def short_silence() -> AudioSegment:
    """1 000 ms of true silence (< transition_max_ms)."""
    return AudioSegment.silent(duration=1_000)


@pytest.fixture
def long_silence() -> AudioSegment:
    """6 000 ms of true silence (> transition_max_ms of 5 000 ms)."""
    return AudioSegment.silent(duration=6_000)


@pytest.fixture
def track_long_silence(speech: AudioSegment, long_silence: AudioSegment) -> AudioSegment:
    """speech | 6 s silence | speech  (total 10 000 ms)."""
    return speech + long_silence + speech


@pytest.fixture
def track_short_silence(speech: AudioSegment, short_silence: AudioSegment) -> AudioSegment:
    """speech | 1 s silence | speech  (total 5 000 ms)."""
    return speech + short_silence + speech


@pytest.fixture
def transition_asset() -> AudioSegment:
    """7 000 ms transition asset — longer than transition_max_ms to verify capping."""
    return sine_tone(880, 7_000, TRANSITION_VOLUME_DB)


@pytest.fixture
def fond_asset() -> AudioSegment:
    """3 000 ms loopable background music clip."""
    return sine_tone(220, 3_000, BED_VOLUME_DB)
