"""
test_audio_engine.py
====================
Unit tests for FlowCast's audio engine (v2).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydub import AudioSegment

from app.audio_engine import (
    MixConfig,
    detect_and_split_by_silence,
    trim_segment_edges,
    build_bed_with_envelope,
    assemble_bulletin,
)

def test_detect_and_split_by_silence(raw_two_segments: AudioSegment) -> None:
    cfg = MixConfig(silence_thresh_db_relative=-16.0, min_silence_len_ms=400)
    segments = detect_and_split_by_silence(raw_two_segments, cfg)
    assert len(segments) == 2
    # Each segment should be roughly 2000ms
    assert 1900 <= len(segments[0]) <= 2100
    assert 1900 <= len(segments[1]) <= 2100

def test_detect_three_segments(raw_three_segments: AudioSegment) -> None:
    cfg = MixConfig(silence_thresh_db_relative=-16.0, min_silence_len_ms=400)
    segments = detect_and_split_by_silence(raw_three_segments, cfg)
    assert len(segments) == 3

def test_trim_segment_edges(speech: AudioSegment) -> None:
    # speech is 2000ms at -6dB. Add 500ms silence to both ends.
    pad = 100
    track = AudioSegment.silent(duration=500) + speech + AudioSegment.silent(duration=500)
    trimmed = trim_segment_edges(track, pad_ms=pad)
    
    # We expect roughly 2000 + 2*100 = 2200ms
    assert 2100 <= len(trimmed) <= 2300

def test_build_bed_with_envelope(fond_asset: AudioSegment) -> None:
    cfg = MixConfig(
        duck_db=-18.0,
        transition_high_db=-3.0,
        transition_total_ms=3000,
        transition_fade_in_ms=1000,
        transition_fade_out_ms=1000,
    )
    # Two segments of 2000ms. 
    # Total bed length should be: 2000 + 3000 (transition) + 2000 = 7000ms
    durations = [2000, 2000]
    bed = build_bed_with_envelope(fond_asset, durations, cfg)
    
    assert len(bed) == 7000
    # The bed should never be completely silent
    assert not math.isinf(bed.dBFS)

def test_assemble_bulletin_mocked(
    raw_two_segments: AudioSegment,
    speech: AudioSegment,
    fond_asset: AudioSegment,
    tmp_path: Path
) -> None:
    # Use speech as intro/outro to simplify
    intro = speech
    outro = speech
    
    # Save raw audio to disk
    raw_path = tmp_path / "raw.mp3"
    raw_two_segments.export(str(raw_path), format="mp3")
    
    # Dummy config
    cfg_path = tmp_path / "source_bank.json"
    cfg_path.write_text("{}")
    
    out_path = tmp_path / "out.mp3"
    
    res = assemble_bulletin(
        raw_path,
        cfg_path,
        out_path,
        intro_asset=intro,
        outro_asset=outro,
        fond_asset=fond_asset
    )
    
    assert res.segments_count == 2
    assert res.transitions_count == 1
    assert out_path.exists()
