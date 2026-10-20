"""
Tests for upload format validation and MP3 conversion.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from app.dependencies import (
    ALLOWED_EXTENSIONS,
    CONVERT_TO_MP3_EXTENSIONS,
    convert_to_mp3,
)


def test_allowed_extensions_contain_m4a_and_mp4():
    assert ".mp3" in ALLOWED_EXTENSIONS
    assert ".wav" in ALLOWED_EXTENSIONS
    assert ".m4a" in ALLOWED_EXTENSIONS
    assert ".ma4" in ALLOWED_EXTENSIONS
    assert ".mp4" in ALLOWED_EXTENSIONS
    assert ".m4a" in CONVERT_TO_MP3_EXTENSIONS
    assert ".ma4" in CONVERT_TO_MP3_EXTENSIONS
    assert ".mp4" in CONVERT_TO_MP3_EXTENSIONS


def test_convert_to_mp3_from_mp4(tmp_path: Path):
    # Create a small synthetic MP4 with audio track
    wav_path = tmp_path / "tone.wav"
    mp4_path = tmp_path / "sample.mp4"
    mp3_path = tmp_path / "converted.mp3"

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1", str(wav_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
            "-i", str(wav_path),
            "-c:v", "libx264", "-c:a", "aac",
            str(mp4_path),
        ],
        check=True,
        capture_output=True,
    )

    result_path = convert_to_mp3(mp4_path, mp3_path)
    assert result_path.exists()
    assert result_path.stat().st_size > 0
    assert result_path.suffix == ".mp3"
