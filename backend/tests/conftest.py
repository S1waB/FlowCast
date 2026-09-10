"""
conftest.py – shared fixtures for FlowCast audio engine tests (v2).

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

FOND_VOLUME_DB: float = -12.0
"""Background music reference level (before ducking is applied)."""


def sine_tone(freq: int, duration_ms: int, volume_db: float) -> AudioSegment:
    """Return a mono sine-wave AudioSegment at *volume_db* dBFS."""
    return Sine(freq).to_audio_segment(duration=duration_ms, volume=volume_db)


# ── Reusable fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def speech() -> AudioSegment:
    """2 000 ms of clear speech-like tone at -6 dBFS."""
    return sine_tone(440, 2_000, SPEECH_VOLUME_DB)


@pytest.fixture
def fond_asset() -> AudioSegment:
    """3 000 ms loopable background music clip at -12 dBFS."""
    return sine_tone(220, 3_000, FOND_VOLUME_DB)


@pytest.fixture
def raw_two_segments(speech: AudioSegment) -> AudioSegment:
    """speech | 1 200 ms silence | speech  — exactly 2 speech segments."""
    return speech + AudioSegment.silent(duration=1_200) + speech


@pytest.fixture
def raw_three_segments(speech: AudioSegment) -> AudioSegment:
    """speech | 800 ms silence | speech | 2 000 ms silence | speech — 3 segments."""
    return (
        speech
        + AudioSegment.silent(duration=800)
        + speech
        + AudioSegment.silent(duration=2_000)
        + speech
    )


@pytest.fixture
def raw_leading_trailing_silence(speech: AudioSegment) -> AudioSegment:
    """500 ms silence | speech | 800 ms silence | speech | 500 ms silence."""
    return (
        AudioSegment.silent(duration=500)
        + speech
        + AudioSegment.silent(duration=800)
        + speech
        + AudioSegment.silent(duration=500)
    )
