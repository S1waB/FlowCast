"""
test_audio_engine.py
====================
Unit tests for FlowCast's audio engine.

Covered assertions
------------------
T1  No transition inserted by insert_transitions may exceed transition_max_ms.
T2  Fade-in and fade-out are exactly 1 000 ms when the silence is long enough
    (≥ transition_max_ms); they are proportionally capped on short silences.
T3  No transition overlaps speech: trans_start ≥ sil_start + min_gap_safety_ms
    and trans_end ≤ sil_end − min_gap_safety_ms.
T4  build_bed returns a segment whose duration equals exactly total_duration_ms,
    with no silent gap at any 500 ms sample point (RMS > 0 throughout).
"""

from __future__ import annotations

import math

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from app.audio_engine import (
    MixConfig,
    TransitionInfo,
    build_bed,
    detect_silences,
    insert_transitions,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def default_cfg(**overrides: object) -> MixConfig:
    """Return a MixConfig with production defaults, optionally overridden."""
    fields = {
        "duck_db": -16.0,
        "transition_max_ms": 5_000,
        "transition_fade_in_ms": 1_000,
        "transition_fade_out_ms": 1_000,
        "silence_thresh_db_relative": -16.0,
        "min_silence_len_ms": 400,
        "min_gap_safety_ms": 100,
    }
    fields.update(overrides)
    return MixConfig(**fields)  # type: ignore[arg-type]


def _run(
    track: AudioSegment,
    transition: AudioSegment,
    cfg: MixConfig | None = None,
) -> tuple[AudioSegment, list[TransitionInfo]]:
    return insert_transitions(track, transition, cfg or default_cfg())


# ─────────────────────────────────────────────────────────────────────────────
# TestDetectSilences
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectSilences:
    """Verify that detect_silences correctly identifies pause positions."""

    def test_single_internal_silence_detected(
        self, track_long_silence: AudioSegment
    ) -> None:
        """A 6 s silence between two speech segments must be detected."""
        thresh = -50.0  # absolute – well below the speech tone
        silences = detect_silences(track_long_silence, thresh, min_silence_len_ms=400)
        assert len(silences) >= 1, "Expected at least one silence"

    def test_silence_boundaries_are_inside_the_gap(
        self, track_long_silence: AudioSegment
    ) -> None:
        """Detected silence must fall within the known 2 000–8 000 ms window."""
        thresh = -50.0
        silences = detect_silences(track_long_silence, thresh, min_silence_len_ms=400)
        sil_start, sil_end = silences[0]
        # Allow ±50 ms tolerance for pydub's seek granularity
        assert sil_start >= 1_950
        assert sil_end <= 8_050

    def test_pure_speech_yields_no_silence(self, speech: AudioSegment) -> None:
        thresh = -50.0
        assert detect_silences(speech, thresh, min_silence_len_ms=400) == []

    def test_silence_shorter_than_min_not_reported(self) -> None:
        track = (
            Sine(440).to_audio_segment(duration=1_000, volume=-6)
            + AudioSegment.silent(duration=200)
            + Sine(440).to_audio_segment(duration=1_000, volume=-6)
        )
        thresh = -50.0
        assert detect_silences(track, thresh, min_silence_len_ms=400) == []

    def test_multiple_silences_detected(self, speech: AudioSegment) -> None:
        track = (
            speech
            + AudioSegment.silent(duration=600)
            + speech
            + AudioSegment.silent(duration=600)
            + speech
        )
        thresh = -50.0
        silences = detect_silences(track, thresh, min_silence_len_ms=400)
        assert len(silences) == 2


# ─────────────────────────────────────────────────────────────────────────────
# TestInsertTransitions
# ─────────────────────────────────────────────────────────────────────────────

class TestInsertTransitions:
    """
    Four primary invariants are tested independently for both long and short
    silences so edge-case truncation logic is exercised.
    """

    # ── T1 – No transition > transition_max_ms ────────────────────────────────

    def test_T1_no_transition_exceeds_max_on_long_silence(
        self,
        track_long_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        """Silence = 6 s > 5 s cap → transition must be exactly 5 000 ms."""
        cfg = default_cfg()
        _, transitions = _run(track_long_silence, transition_asset, cfg)
        assert transitions, "Expected at least one transition to be inserted"
        for t in transitions:
            assert t.duration_ms <= cfg.transition_max_ms, (
                f"Transition duration {t.duration_ms} ms exceeds "
                f"transition_max_ms={cfg.transition_max_ms} ms"
            )

    def test_T1_no_transition_exceeds_max_on_short_silence(
        self,
        track_short_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        """Silence = 1 s < 5 s → transition must also be ≤ 5 000 ms."""
        cfg = default_cfg()
        _, transitions = _run(track_short_silence, transition_asset, cfg)
        for t in transitions:
            assert t.duration_ms <= cfg.transition_max_ms

    def test_T1_no_transition_exceeds_max_with_multiple_silences(
        self, speech: AudioSegment, transition_asset: AudioSegment
    ) -> None:
        """Three silences of varying lengths – none may exceed the cap."""
        track = (
            speech
            + AudioSegment.silent(duration=800)
            + speech
            + AudioSegment.silent(duration=6_000)
            + speech
            + AudioSegment.silent(duration=3_000)
            + speech
        )
        cfg = default_cfg()
        _, transitions = _run(track, transition_asset, cfg)
        for t in transitions:
            assert t.duration_ms <= cfg.transition_max_ms, (
                f"duration_ms={t.duration_ms} > transition_max_ms={cfg.transition_max_ms}"
            )

    # ── T2 – Fades exactly 1 000 ms on full-length transition ─────────────────

    def test_T2_fade_in_is_exactly_1000ms_on_long_silence(
        self,
        track_long_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        """
        When silence gives enough room for the full 5 s transition,
        fade_in must equal transition_fade_in_ms (1 000 ms).
        """
        cfg = default_cfg()
        _, transitions = _run(track_long_silence, transition_asset, cfg)
        full_length = [t for t in transitions if t.duration_ms == cfg.transition_max_ms]
        assert full_length, "Expected a full-length (5 000 ms) transition"
        for t in full_length:
            assert t.fade_in_ms == cfg.transition_fade_in_ms, (
                f"fade_in={t.fade_in_ms} ms, expected {cfg.transition_fade_in_ms} ms"
            )

    def test_T2_fade_out_is_exactly_1000ms_on_long_silence(
        self,
        track_long_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        cfg = default_cfg()
        _, transitions = _run(track_long_silence, transition_asset, cfg)
        full_length = [t for t in transitions if t.duration_ms == cfg.transition_max_ms]
        for t in full_length:
            assert t.fade_out_ms == cfg.transition_fade_out_ms, (
                f"fade_out={t.fade_out_ms} ms, expected {cfg.transition_fade_out_ms} ms"
            )

    def test_T2_fades_capped_on_short_silence(
        self,
        track_short_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        """
        Short silence → transition shorter than 2 000 ms → each fade must be
        ≤ transition_duration // 2 (they must not overlap each other).
        """
        cfg = default_cfg()
        _, transitions = _run(track_short_silence, transition_asset, cfg)
        for t in transitions:
            half = t.duration_ms // 2
            assert t.fade_in_ms <= half, (
                f"fade_in {t.fade_in_ms} ms > half-duration {half} ms"
            )
            assert t.fade_out_ms <= half, (
                f"fade_out {t.fade_out_ms} ms > half-duration {half} ms"
            )

    def test_T2_fades_sum_le_duration(
        self,
        track_short_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        """Fade-in + fade-out must never exceed the transition duration."""
        _, transitions = _run(track_short_silence, transition_asset)
        for t in transitions:
            assert t.fade_in_ms + t.fade_out_ms <= t.duration_ms

    # ── T3 – No transition overlaps speech ────────────────────────────────────

    def test_T3_no_speech_overlap_long_silence(
        self,
        track_long_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        """
        trans_start ≥ sil_start + min_gap_safety_ms
        trans_end   ≤ sil_end   − min_gap_safety_ms
        """
        cfg = default_cfg()
        _, transitions = _run(track_long_silence, transition_asset, cfg)
        for t in transitions:
            safe_start = t.silence_start_ms + cfg.min_gap_safety_ms
            safe_end = t.silence_end_ms - cfg.min_gap_safety_ms
            assert t.trans_start_ms >= safe_start, (
                f"Transition starts at {t.trans_start_ms} ms, "
                f"must be ≥ safe_start {safe_start} ms"
            )
            assert t.trans_end_ms <= safe_end, (
                f"Transition ends at {t.trans_end_ms} ms, "
                f"must be ≤ safe_end {safe_end} ms"
            )

    def test_T3_no_speech_overlap_short_silence(
        self,
        track_short_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        cfg = default_cfg()
        _, transitions = _run(track_short_silence, transition_asset, cfg)
        for t in transitions:
            safe_start = t.silence_start_ms + cfg.min_gap_safety_ms
            safe_end = t.silence_end_ms - cfg.min_gap_safety_ms
            assert t.trans_start_ms >= safe_start
            assert t.trans_end_ms <= safe_end

    def test_T3_no_speech_overlap_multiple_silences(
        self, speech: AudioSegment, transition_asset: AudioSegment
    ) -> None:
        """Invariant holds across all three silences of different lengths."""
        track = (
            speech
            + AudioSegment.silent(duration=800)
            + speech
            + AudioSegment.silent(duration=6_000)
            + speech
            + AudioSegment.silent(duration=2_500)
            + speech
        )
        cfg = default_cfg()
        _, transitions = _run(track, transition_asset, cfg)
        for t in transitions:
            safe_start = t.silence_start_ms + cfg.min_gap_safety_ms
            safe_end = t.silence_end_ms - cfg.min_gap_safety_ms
            assert t.trans_start_ms >= safe_start
            assert t.trans_end_ms <= safe_end

    # ── Additional invariants ─────────────────────────────────────────────────

    def test_voice_track_duration_unchanged(
        self,
        track_long_silence: AudioSegment,
        transition_asset: AudioSegment,
    ) -> None:
        """overlay() must never change the total duration of the voice track."""
        original_len = len(track_long_silence)
        result, _ = _run(track_long_silence, transition_asset)
        assert len(result) == original_len

    def test_no_transition_when_silence_too_narrow(self) -> None:
        """A silence narrower than 2 × min_gap_safety_ms is skipped entirely."""
        speech = Sine(440).to_audio_segment(duration=1_000, volume=-6)
        track = speech + AudioSegment.silent(duration=150) + speech
        cfg = default_cfg(min_gap_safety_ms=100)  # 2×100 = 200 > 150 ms silence
        transition = Sine(880).to_audio_segment(duration=3_000, volume=-20)
        _, transitions = _run(track, transition, cfg)
        assert transitions == [], "Should not insert a transition into a 150 ms silence"

    def test_no_transition_on_all_speech(
        self, speech: AudioSegment, transition_asset: AudioSegment
    ) -> None:
        """A track with no silence gets no transitions."""
        _, transitions = _run(speech, transition_asset)
        assert transitions == []

    def test_completely_silent_track_is_returned_unchanged(
        self, transition_asset: AudioSegment
    ) -> None:
        """A completely silent track has dBFS = -inf; function returns it as-is."""
        silent_track = AudioSegment.silent(duration=5_000)
        result, transitions = _run(silent_track, transition_asset)
        assert transitions == []
        assert len(result) == len(silent_track)


# ─────────────────────────────────────────────────────────────────────────────
# TestBuildBed
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildBed:
    """
    T4 – The bed must be exactly total_duration_ms long and contain no silent
    gaps at any sampled point.
    """

    @pytest.mark.parametrize("total_ms", [500, 1_000, 3_000, 7_777, 10_000])
    def test_T4_bed_duration_exact(
        self, fond_asset: AudioSegment, total_ms: int
    ) -> None:
        """len(bed) must equal total_duration_ms to the millisecond."""
        bed = build_bed(fond_asset, total_ms, duck_db=-16.0)
        assert len(bed) == total_ms, (
            f"Expected bed duration {total_ms} ms, got {len(bed)} ms"
        )

    def test_T4_bed_duration_equals_voice_track_duration(
        self,
        track_long_silence: AudioSegment,
        transition_asset: AudioSegment,
        fond_asset: AudioSegment,
    ) -> None:
        """
        After insert_transitions, the bed built from the processed voice track
        must be exactly as long as that track (invariant for the full pipeline).
        """
        voice_with_trans, _ = insert_transitions(
            track_long_silence, transition_asset, default_cfg()
        )
        bed = build_bed(fond_asset, len(voice_with_trans), duck_db=-16.0)
        assert len(bed) == len(voice_with_trans), (
            f"Bed duration {len(bed)} ms ≠ voice track duration "
            f"{len(voice_with_trans)} ms"
        )

    def test_T4_bed_never_interrupted(self, fond_asset: AudioSegment) -> None:
        """
        No 500 ms window inside the bed may be silent (RMS = 0).
        This proves the fond loops seamlessly without any gap at loop boundaries.
        """
        total_ms = 10_000
        bed = build_bed(fond_asset, total_ms, duck_db=-16.0)

        chunk_size = 500
        for start in range(0, total_ms - chunk_size + 1, chunk_size):
            chunk = bed[start : start + chunk_size]
            assert chunk.rms > 0, (
                f"Bed is silent in window [{start}, {start + chunk_size}] ms"
            )

    def test_T4_bed_covers_loop_boundary(self, fond_asset: AudioSegment) -> None:
        """
        The RMS around the loop-back point (multiple of fond_asset length) must
        be non-zero to confirm there is no click or gap at the seam.
        """
        asset_len = len(fond_asset)   # 3 000 ms
        total_ms = asset_len * 2 + 500  # crosses two loop boundaries
        bed = build_bed(fond_asset, total_ms, duck_db=-16.0)

        # Sample a 200 ms window centred on the first loop boundary
        boundary = asset_len
        window_start = max(0, boundary - 100)
        window_end = min(total_ms, boundary + 100)
        chunk = bed[window_start:window_end]
        assert chunk.rms > 0, "Bed is silent at the loop boundary"

    def test_T4_bed_is_ducked(self, fond_asset: AudioSegment) -> None:
        """Bed must be quieter than the original fond_asset."""
        bed = build_bed(fond_asset, len(fond_asset), duck_db=-16.0)
        assert bed.dBFS < fond_asset.dBFS, (
            f"Bed dBFS {bed.dBFS:.1f} should be less than "
            f"fond_asset dBFS {fond_asset.dBFS:.1f}"
        )

    def test_T4_empty_fond_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            build_bed(AudioSegment.empty(), 5_000, duck_db=-16.0)

    def test_T4_zero_duration_raises(self, fond_asset: AudioSegment) -> None:
        with pytest.raises(ValueError, match="positive"):
            build_bed(fond_asset, 0, duck_db=-16.0)

    @pytest.mark.parametrize("total_ms", [1, 499, 3_001])
    def test_T4_non_multiple_durations_exact(
        self, fond_asset: AudioSegment, total_ms: int
    ) -> None:
        """Durations that are not multiples of fond_asset length must still be exact."""
        bed = build_bed(fond_asset, total_ms, duck_db=-16.0)
        assert len(bed) == total_ms
