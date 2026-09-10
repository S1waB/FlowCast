"""
FlowCast – Audio Engine (v2)
============================
Implements the exact algorithm from the specification:

  STEP 1 – detect_and_split_by_silence
      Detect all silences in the raw audio and extract speech segments
      (the intervals between silences), excluding any silence.

  STEP 2 – trim_segment_edges
      For each individual speech segment, strip residual silence from its
      own leading and trailing edges (with a segment_trim_pad_ms guard).

  STEP 3 – assemble_bulletin
      a) Intro (fixed, no fond underneath)
      b) For each segment i:
           – fond at duck_db underneath
           – if i+1 exists: TRANSITION of exactly transition_total_ms,
             built from the fond itself (no external file):
               fond rises duck_db → transition_high_db (fade-in)
               stays high
               falls back to duck_db (fade-out)
      c) Outro (crossfade from fond fade-out)

Public API
----------
detect_and_split_by_silence(raw_audio, cfg) -> list[AudioSegment]
trim_segment_edges(segment, pad_ms) -> AudioSegment
build_bed_with_envelope(fond_asset, segment_durations, cfg) -> AudioSegment
assemble_bulletin(raw_audio_path, config_path, output_path) -> AssemblyResult
loudness_normalize(input_path, output_path, target_lufs) -> Path
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_silence as _pydub_detect_silence


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MixConfig:
    """
    Mixing parameters loaded from source_bank.json.

    All *_ms fields are milliseconds; *_db fields are dBFS.
    """

    # Asset paths (relative to backend root)
    intro_path: str = "source_bank/intro.mp3"
    outro_path: str = "source_bank/outro.mp3"
    fond_path:  str = "source_bank/fond.mp3"

    # Ducking & transition envelope
    duck_db: float = -18.0
    """Fond gain under speech segments."""

    transition_high_db: float = -3.0
    """Fond peak gain during a transition."""

    transition_total_ms: int = 3_000
    """Total transition duration — always exactly this, regardless of original silence length."""

    transition_fade_in_ms: int = 1_000
    """Fade from duck_db → transition_high_db at the start of a transition."""

    transition_fade_out_ms: int = 1_000
    """Fade from transition_high_db → duck_db at the end of a transition."""

    # Silence detection
    silence_thresh_db_relative: float = -16.0
    """Silence threshold relative to the clip's mean dBFS (always negative)."""

    min_silence_len_ms: int = 400
    """Minimum contiguous silence length (ms) to be recognised as a gap."""

    # Segment trimming
    segment_trim_pad_ms: int = 100
    """Safety pad kept at each edge when trimming individual segment silences."""

    # ── factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_json(cls, path: str | Path) -> "MixConfig":
        """Load from source_bank.json (flat structure per spec)."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            intro_path=raw.get("intro", cls.intro_path),
            outro_path=raw.get("outro", cls.outro_path),
            fond_path=raw.get("fond", cls.fond_path),
            duck_db=float(raw.get("duck_db", cls.duck_db)),
            transition_high_db=float(raw.get("transition_high_db", cls.transition_high_db)),
            transition_total_ms=int(raw.get("transition_total_ms", cls.transition_total_ms)),
            transition_fade_in_ms=int(raw.get("transition_fade_in_ms", cls.transition_fade_in_ms)),
            transition_fade_out_ms=int(raw.get("transition_fade_out_ms", cls.transition_fade_out_ms)),
            silence_thresh_db_relative=float(
                raw.get("silence_thresh_db_relative", cls.silence_thresh_db_relative)
            ),
            min_silence_len_ms=int(raw.get("min_silence_len_ms", cls.min_silence_len_ms)),
            segment_trim_pad_ms=int(raw.get("segment_trim_pad_ms", cls.segment_trim_pad_ms)),
        )


@dataclass(frozen=True)
class AssemblyResult:
    """Rich return value from :func:`assemble_bulletin`."""

    output_path: Path
    segments_count: int
    """Number of speech segments detected in the raw audio."""

    transitions_count: int
    """Number of transitions inserted (= segments_count - 1)."""

    duration_ms: int
    """Total duration of the final bulletin in ms."""


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 – detect_and_split_by_silence
# ─────────────────────────────────────────────────────────────────────────────

def detect_and_split_by_silence(
    raw_audio: AudioSegment,
    cfg: MixConfig,
) -> list[AudioSegment]:
    """
    Detect all silences in *raw_audio* and return the speech segments between them.

    Algorithm
    ---------
    1. Compute the absolute silence threshold from the clip's mean dBFS and
       ``cfg.silence_thresh_db_relative``.
    2. Find all ``[silence_start, silence_end]`` intervals using pydub.
    3. The speech segments are the gaps **between** silences (plus the audio
       before the first silence and after the last silence, if non-empty).
    4. Leading silence at the very start of the file and trailing silence at
       the very end are excluded — they are replaced by intro/outro, never by
       a transition.

    Parameters
    ----------
    raw_audio:
        The raw input :class:`~pydub.AudioSegment`.
    cfg:
        :class:`MixConfig` carrying ``silence_thresh_db_relative`` and
        ``min_silence_len_ms``.

    Returns
    -------
    list[AudioSegment]
        Ordered list of speech-only segments.  Each segment may still have
        a little residual silence at its edges; call :func:`trim_segment_edges`
        on each one before assembling.
    """
    mean_dbfs = raw_audio.dBFS
    if math.isinf(mean_dbfs):
        # Completely silent file → no speech segments
        return []

    abs_thresh = mean_dbfs + cfg.silence_thresh_db_relative

    raw_silences: list[list[int]] = _pydub_detect_silence(
        raw_audio,
        min_silence_len=cfg.min_silence_len_ms,
        silence_thresh=abs_thresh,
        seek_step=1,
    )
    silences: list[tuple[int, int]] = [(int(s), int(e)) for s, e in raw_silences]

    total_ms = len(raw_audio)

    # Build speech regions as the complement of silence regions
    speech_regions: list[tuple[int, int]] = []
    cursor = 0

    for sil_start, sil_end in silences:
        if sil_start > cursor:
            speech_regions.append((cursor, sil_start))
        cursor = sil_end

    # Final segment after the last silence
    if cursor < total_ms:
        speech_regions.append((cursor, total_ms))

    # Extract as AudioSegment slices
    segments = [raw_audio[start:end] for start, end in speech_regions if end > start]
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 – trim_segment_edges
# ─────────────────────────────────────────────────────────────────────────────

def trim_segment_edges(segment: AudioSegment, pad_ms: int = 100) -> AudioSegment:
    """
    Remove residual silence from the leading and trailing edges of *segment*.

    Works on the segment **in isolation** (never on the full concatenated
    track), so a silence that happens to be the quietest part of one segment
    does not contaminate the trimming threshold of another.

    The ``pad_ms`` guard ensures we never trim right up to the first/last
    speech sample — a small safety margin is always preserved.

    Parameters
    ----------
    segment:
        Individual speech :class:`~pydub.AudioSegment` to trim.
    pad_ms:
        Safety margin (ms) kept on each side after trimming.  Defaults to 100.

    Returns
    -------
    AudioSegment — the trimmed segment, or the original if no trimming was needed.
    """
    if len(segment) == 0:
        return segment

    mean_dbfs = segment.dBFS
    if math.isinf(mean_dbfs):
        return AudioSegment.empty()

    # Use a fairly aggressive threshold: 20 dB below the segment's own mean
    # so only true silence (not quiet-but-present speech) is trimmed.
    thresh = mean_dbfs - 20.0

    silences = _pydub_detect_silence(
        segment,
        min_silence_len=50,   # short threshold — we just want edge silences
        silence_thresh=thresh,
        seek_step=1,
    )

    if not silences:
        return segment

    silences_t = [(int(s), int(e)) for s, e in silences]
    total = len(segment)

    trim_start = 0
    trim_end = total

    # Leading silence: if first silence touches the start (within pad_ms tolerance)
    if silences_t[0][0] < pad_ms:
        trim_start = max(0, silences_t[0][1] - pad_ms)

    # Trailing silence: if last silence touches the end
    if silences_t[-1][1] > total - pad_ms:
        trim_end = min(total, silences_t[-1][0] + pad_ms)

    if trim_start >= trim_end:
        return segment  # degenerate, return as-is

    return segment[trim_start:trim_end]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3a – build_bed_with_envelope
# ─────────────────────────────────────────────────────────────────────────────

def build_bed_with_envelope(
    fond_asset: AudioSegment,
    segment_durations: list[int],
    cfg: MixConfig,
) -> AudioSegment:
    """
    Build a **continuous** looped fond track whose gain envelope matches the
    full assembly structure (segments + transitions).

    The envelope — seen as a gain curve over time — is:

    ::

        For each segment i (duration D_i):
          [0 … D_i]          → duck_db   (under speech)

        Between segment i and i+1:
          [0 … fade_in_ms]   → duck_db → transition_high_db  (rise)
          [fade_in_ms … T-fade_out_ms] → transition_high_db   (flat peak)
          [T-fade_out_ms … T]→ transition_high_db → duck_db  (fall)
          where T = transition_total_ms

        No transition after the last segment.

    The fond loops seamlessly underneath the entire structure; gain changes
    are applied by constructing alternating ducked/loud/transition slices
    and overlaying them.

    Parameters
    ----------
    fond_asset:
        Source background music clip (looped internally to required length).
    segment_durations:
        List of durations in ms for each trimmed speech segment, in order.
    cfg:
        :class:`MixConfig` with duck/transition parameters.

    Returns
    -------
    AudioSegment whose length equals
    ``sum(segment_durations) + (len(segment_durations) - 1) * transition_total_ms``.
    """
    if not segment_durations:
        return AudioSegment.empty()

    n_transitions = max(0, len(segment_durations) - 1)
    total_ms = sum(segment_durations) + n_transitions * cfg.transition_total_ms

    if len(fond_asset) == 0:
        raise ValueError("fond_asset must not be empty")

    # Build the raw (unmodified) looped bed at full volume
    loops_needed = math.ceil(total_ms / len(fond_asset))
    bed_raw: AudioSegment = (fond_asset * loops_needed)[:total_ms]

    # Pre-build level references
    bed_ducked = bed_raw + cfg.duck_db
    bed_high   = bed_raw + cfg.transition_high_db

    fade_in_ms  = min(cfg.transition_fade_in_ms,  cfg.transition_total_ms // 2)
    fade_out_ms = min(cfg.transition_fade_out_ms, cfg.transition_total_ms // 2)
    flat_ms     = cfg.transition_total_ms - fade_in_ms - fade_out_ms

    parts: list[AudioSegment] = []
    cursor = 0

    for i, dur in enumerate(segment_durations):
        # ── Speech segment: fond at duck_db ───────────────────────────────────
        seg_end = cursor + dur
        parts.append(bed_ducked[cursor:seg_end])
        cursor = seg_end

        # ── Transition (not after the last segment) ───────────────────────────
        if i < len(segment_durations) - 1:
            t_start = cursor

            # Phase 1: fade-in from duck_db → transition_high_db
            if fade_in_ms > 0:
                fi_end = t_start + fade_in_ms
                duck_ramp = bed_ducked[t_start:fi_end].fade_out(fade_in_ms)
                high_ramp = bed_high[t_start:fi_end].fade_in(fade_in_ms)
                parts.append(duck_ramp.overlay(high_ramp))
                cursor = fi_end

            # Phase 2: flat at transition_high_db
            if flat_ms > 0:
                flat_end = cursor + flat_ms
                parts.append(bed_high[cursor:flat_end])
                cursor = flat_end

            # Phase 3: fade-out from transition_high_db → duck_db
            if fade_out_ms > 0:
                fo_end = cursor + fade_out_ms
                high_ramp = bed_high[cursor:fo_end].fade_out(fade_out_ms)
                duck_ramp = bed_ducked[cursor:fo_end].fade_in(fade_out_ms)
                parts.append(high_ramp.overlay(duck_ramp))
                cursor = fo_end

    # Concatenate and ensure exact length
    final_bed: AudioSegment = AudioSegment.empty()
    for p in parts:
        final_bed += p

    delta = total_ms - len(final_bed)
    if delta > 0:
        final_bed += AudioSegment.silent(
            duration=delta, frame_rate=final_bed.frame_rate
        )
    elif delta < 0:
        final_bed = final_bed[:total_ms]

    return final_bed


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3b – assemble_bulletin
# ─────────────────────────────────────────────────────────────────────────────

def assemble_bulletin(
    raw_audio_path: str | Path,
    config_path: str | Path,
    output_path: str | Path,
    *,
    # Optional asset injection for unit tests (avoids real files on disk)
    intro_asset: AudioSegment | None = None,
    outro_asset: AudioSegment | None = None,
    fond_asset:  AudioSegment | None = None,
) -> AssemblyResult:
    """
    Full bulletin assembly pipeline.

    Pipeline (exact order)
    ----------------------
    1. Load config → :class:`MixConfig`.
    2. Load intro, outro, fond assets.
    3. Load raw audio from *raw_audio_path*.
    4. :func:`detect_and_split_by_silence` → list of speech segments.
    5. :func:`trim_segment_edges` on each segment individually.
    6. :func:`build_bed_with_envelope` → continuous fond track with envelope.
    7. Mix each speech segment with the corresponding fond slice (bed overlay).
    8. Interleave mixed segments and silence-replaced-by-transition slices
       (transition = the fond itself at high volume).
    9. Prepend intro (fixed, no fond underneath).
    10. Append outro (fond fade-out crossfade with outro fade-in).
    11. Export stereo MP3 @ 192 kbps.

    Returns
    -------
    :class:`AssemblyResult` with segments_count, transitions_count, duration_ms.
    """
    cfg = MixConfig.from_json(config_path)
    backend_root = Path(config_path).parent.parent

    def _load(asset: AudioSegment | None, rel_path: str) -> AudioSegment:
        if asset is not None:
            return asset
        full = backend_root / rel_path
        if not full.exists():
            raise FileNotFoundError(str(full))
        return AudioSegment.from_file(str(full))

    intro      = _load(intro_asset, cfg.intro_path)
    outro      = _load(outro_asset, cfg.outro_path)
    fond       = _load(fond_asset,  cfg.fond_path)

    # ── Load raw audio ────────────────────────────────────────────────────────
    raw = AudioSegment.from_file(str(raw_audio_path))

    # ── STEP 1: detect & split by silence ─────────────────────────────────────
    segments = detect_and_split_by_silence(raw, cfg)

    if not segments:
        raise ValueError(
            "No speech segments detected in the uploaded audio. "
            "Check the file or adjust silence_thresh_db_relative / min_silence_len_ms."
        )

    # ── STEP 2: trim each segment individually ────────────────────────────────
    segments = [trim_segment_edges(seg, cfg.segment_trim_pad_ms) for seg in segments]
    # Drop segments that become empty after trimming
    segments = [seg for seg in segments if len(seg) > 0]

    if not segments:
        raise ValueError("All speech segments were empty after trimming.")

    n_segs = len(segments)
    n_trans = n_segs - 1
    seg_durations = [len(s) for s in segments]

    # ── STEP 3: build continuous fond bed with gain envelope ──────────────────
    bed = build_bed_with_envelope(fond, seg_durations, cfg)

    # ── STEP 4: mix speech over the correct bed slice, then interleave ────────
    body: AudioSegment = AudioSegment.empty()
    bed_cursor = 0

    for i, seg in enumerate(segments):
        dur = seg_durations[i]

        # Speech segment: overlay fond (already ducked) + voice
        seg_bed = bed[bed_cursor : bed_cursor + dur]
        body += seg_bed.overlay(seg)
        bed_cursor += dur

        # Transition (not after last segment): pure fond at envelope peak
        if i < n_segs - 1:
            t_ms = cfg.transition_total_ms
            trans_bed = bed[bed_cursor : bed_cursor + t_ms]
            body += trans_bed
            bed_cursor += t_ms

    # ── STEP 5: prepend intro (no fond underneath) ────────────────────────────
    INTRO_CROSSFADE_MS = min(len(intro), 4_000)
    result = intro.append(body, crossfade=INTRO_CROSSFADE_MS)

    # ── STEP 6: append outro (crossfade with body end) ────────────────────────
    OUTRO_CROSSFADE_MS = min(len(outro), 1_000)
    result = result.append(outro, crossfade=OUTRO_CROSSFADE_MS)

    # ── Ensure stereo ─────────────────────────────────────────────────────────
    result = result.set_channels(2)

    # ── Export ────────────────────────────────────────────────────────────────
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.export(str(out), format="mp3", bitrate="192k")

    return AssemblyResult(
        output_path=out,
        segments_count=n_segs,
        transitions_count=n_trans,
        duration_ms=len(result),
    )


# ─────────────────────────────────────────────────────────────────────────────
# loudness_normalize
# ─────────────────────────────────────────────────────────────────────────────

def loudness_normalize(
    input_path: str | Path,
    output_path: str | Path,
    target_lufs: float = -16.0,
) -> Path:
    """
    Normalise the integrated loudness of an audio file to *target_lufs* LUFS
    using ffmpeg's ``loudnorm`` filter (EBU R128 / ITU-R BS.1770-4).

    Parameters
    ----------
    input_path:
        Source audio file.
    output_path:
        Destination path (parent directories created automatically).
    target_lufs:
        Target integrated loudness (default ``-16.0`` LUFS).

    Returns
    -------
    :class:`~pathlib.Path` pointing to the normalised file.

    Raises
    ------
    subprocess.CalledProcessError
        If ffmpeg exits with a non-zero code.
    """
    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "192k",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return dst
