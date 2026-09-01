"""
FlowCast – Audio Engine
=======================
All audio-processing primitives for the bulletin auto-mixer.

Public API
----------
detect_silences(audio, silence_thresh_db, min_silence_len_ms)
    → list[tuple[int, int]]

insert_transitions(voice_track, transition_asset, cfg)
    → tuple[AudioSegment, list[TransitionInfo]]

build_bed(fond_asset, total_duration_ms, duck_db)
    → AudioSegment

assemble_bulletin(voice_clip_paths, config_path, output_path, *, ...)
    → Path

loudness_normalize(input_path, output_path, target_lufs)
    → Path
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
    Mixing parameters loaded from source_bank.json (or set programmatically).

    All *_ms fields are in milliseconds; *_db fields are in dBFS.
    """

    duck_db: float = -16.0
    """Gain applied to the background bed (duck level)."""

    transition_max_ms: int = 5_000
    """Hard cap on the transition clip duration placed in a silence."""

    transition_fade_in_ms: int = 1_000
    """Desired fade-in on every transition (may be shorter on narrow silences)."""

    transition_fade_out_ms: int = 1_000
    """Desired fade-out on every transition (may be shorter on narrow silences)."""

    silence_thresh_db_relative: float = -16.0
    """Silence threshold *relative* to the clip's mean dBFS (always negative)."""

    min_silence_len_ms: int = 400
    """Minimum gap length to be reported as a silence."""

    min_gap_safety_ms: int = 100
    """Minimum margin kept between the transition edge and the nearest speech."""

    # ── factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_json(cls, path: str | Path) -> "MixConfig":
        """Instantiate from a ``source_bank.json`` file."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        d = raw.get("defaults", {})
        return cls(
            duck_db=float(d.get("duck_db", cls.duck_db)),
            transition_max_ms=int(d.get("transition_max_ms", cls.transition_max_ms)),
            transition_fade_in_ms=int(d.get("transition_fade_in_ms", cls.transition_fade_in_ms)),
            transition_fade_out_ms=int(d.get("transition_fade_out_ms", cls.transition_fade_out_ms)),
            silence_thresh_db_relative=float(
                d.get("silence_thresh_db_relative", cls.silence_thresh_db_relative)
            ),
            min_silence_len_ms=int(d.get("min_silence_len_ms", cls.min_silence_len_ms)),
            min_gap_safety_ms=int(d.get("min_gap_safety_ms", cls.min_gap_safety_ms)),
        )


@dataclass(frozen=True)
class AssemblyResult:
    """
    Rich return value from :func:`assemble_bulletin`.

    Attributes
    ----------
    output_path:
        Absolute path to the exported MP3.
    transitions_count:
        Number of transition clips that were overlaid on silences.
    duration_ms:
        Total duration of the final bulletin (intro + body + outro) in ms.
    """

    output_path: Path
    transitions_count: int
    duration_ms: int


@dataclass(frozen=True)
class TransitionInfo:
    """
    Metadata describing a single transition that was overlaid on a silence.

    This is returned alongside the processed audio by :func:`insert_transitions`
    so callers (and tests) can inspect exact boundaries without re-analysing the
    audio waveform.
    """

    silence_start_ms: int
    """Start of the detected silence this transition fills."""

    silence_end_ms: int
    """End of the detected silence this transition fills."""

    trans_start_ms: int
    """Absolute position (ms) where the transition clip begins in the track."""

    trans_end_ms: int
    """Absolute position (ms) where the transition clip ends in the track."""

    duration_ms: int
    """Actual (possibly truncated) duration of the clip that was overlaid."""

    fade_in_ms: int
    """Fade-in actually applied (may be < transition_fade_in_ms on short silences)."""

    fade_out_ms: int
    """Fade-out actually applied (may be < transition_fade_out_ms on short silences)."""


# ─────────────────────────────────────────────────────────────────────────────
# 1. detect_silences
# ─────────────────────────────────────────────────────────────────────────────

def detect_silences(
    audio: AudioSegment,
    silence_thresh_db: float,
    min_silence_len_ms: int,
) -> list[tuple[int, int]]:
    """
    Detect all silent intervals anywhere inside *audio*.

    Works on the **full** segment in a single pass, so it finds silences both
    between clips (after concatenation) and inside a single clip where a pause
    exceeds *min_silence_len_ms*.

    Parameters
    ----------
    audio:
        The :class:`~pydub.AudioSegment` to analyse.
    silence_thresh_db:
        Absolute dBFS level below which samples are considered silent.
        Compute as ``audio.dBFS + cfg.silence_thresh_db_relative`` to make it
        relative to the recording's average loudness.
    min_silence_len_ms:
        Minimum contiguous silent length (ms) required to be reported.

    Returns
    -------
    list[tuple[int, int]]
        Sorted list of ``(start_ms, end_ms)`` intervals.
    """
    raw: list[list[int]] = _pydub_detect_silence(
        audio,
        min_silence_len=min_silence_len_ms,
        silence_thresh=silence_thresh_db,
        seek_step=1,
    )
    return [(int(s), int(e)) for s, e in raw]


# ─────────────────────────────────────────────────────────────────────────────
# 2. insert_transitions
# ─────────────────────────────────────────────────────────────────────────────

def insert_transitions(
    voice_track: AudioSegment,
    transition_asset: AudioSegment,
    cfg: MixConfig,
) -> tuple[AudioSegment, list[TransitionInfo]]:
    """
    Overlay a transition jingle centred on every detected silence in *voice_track*.

    Placement rules
    ~~~~~~~~~~~~~~~
    * A ``min_gap_safety_ms`` margin is preserved on each side of the transition
      so it never overlaps speech.
    * The transition duration is capped at ``transition_max_ms`` (5 000 ms).
    * **Short silence** (available space < ``transition_max_ms``):
      The transition is trimmed *symmetrically* to fit entirely inside the safe
      zone.  The total duration of *voice_track* never increases.
    * **Long silence** (available space ≥ ``transition_max_ms``):
      The 5 s transition is placed centred in the safe zone; the leftover silence
      on both sides is filled by the bed (built separately), so there is never
      real silence in the final mix.
    * Fade-in / fade-out are each capped at ``transition_duration // 2`` so they
      never overlap each other on very short transitions.

    The returned :class:`~pydub.AudioSegment` has **the same duration** as the
    input *voice_track* because we overlay rather than splice.

    Returns
    -------
    (modified_voice_track, list[TransitionInfo])
        The second element exposes every transition's exact boundaries for
        testing and logging.
    """
    # Guard: completely silent track has dBFS = -inf; skip gracefully.
    mean_dbfs = voice_track.dBFS
    if math.isinf(mean_dbfs):
        return voice_track, []

    abs_thresh = mean_dbfs + cfg.silence_thresh_db_relative

    silences = detect_silences(voice_track, abs_thresh, cfg.min_silence_len_ms)

    result = voice_track
    inserted: list[TransitionInfo] = []

    for sil_start, sil_end in silences:
        # ── Determine the safe zone ───────────────────────────────────────────
        safe_start = sil_start + cfg.min_gap_safety_ms
        safe_end = sil_end - cfg.min_gap_safety_ms
        available_ms = safe_end - safe_start

        if available_ms <= 0:
            # Silence too short even for the safety margins – skip.
            continue

        # ── Clip duration ─────────────────────────────────────────────────────
        trans_duration = min(cfg.transition_max_ms, available_ms)

        # ── Centre in the safe zone ───────────────────────────────────────────
        center = (safe_start + safe_end) // 2
        trans_start = center - trans_duration // 2
        trans_end = trans_start + trans_duration

        # Clamp to safe zone edges (handles odd-length rounding)
        trans_start = max(trans_start, safe_start)
        trans_end = min(trans_end, safe_end)
        trans_duration = trans_end - trans_start  # recompute after clamp

        # ── Trim asset ────────────────────────────────────────────────────────
        trans_clip: AudioSegment = transition_asset[:trans_duration]

        # ── Fades ─────────────────────────────────────────────────────────────
        half = trans_duration // 2
        fade_in = min(cfg.transition_fade_in_ms, half)
        fade_out = min(cfg.transition_fade_out_ms, half)

        trans_clip = trans_clip.fade_in(fade_in).fade_out(fade_out)

        # ── Overlay (duration of result never changes) ────────────────────────
        result = result.overlay(trans_clip, position=trans_start)

        inserted.append(
            TransitionInfo(
                silence_start_ms=sil_start,
                silence_end_ms=sil_end,
                trans_start_ms=trans_start,
                trans_end_ms=trans_end,
                duration_ms=trans_duration,
                fade_in_ms=fade_in,
                fade_out_ms=fade_out,
            )
        )

    return result, inserted


# ─────────────────────────────────────────────────────────────────────────────
# 3. build_bed
# ─────────────────────────────────────────────────────────────────────────────

def build_bed(
    fond_asset: AudioSegment,
    total_duration_ms: int,
    duck_db: float,
) -> AudioSegment:
    """
    Loop *fond_asset* seamlessly until it fills *total_duration_ms*, then duck.

    The bed is **exactly** ``total_duration_ms`` long so it can be mixed under
    the whole vocal montage without any gap, including during transitions.

    Parameters
    ----------
    fond_asset:
        Background music clip to loop.  Must be non-empty.
    total_duration_ms:
        Target duration in milliseconds (positive integer).
    duck_db:
        Gain delta applied to the looped bed (negative value, e.g. ``-16``).

    Returns
    -------
    AudioSegment of length exactly *total_duration_ms*.
    """
    if len(fond_asset) == 0:
        raise ValueError("fond_asset must not be empty")
    if total_duration_ms <= 0:
        raise ValueError("total_duration_ms must be a positive integer")

    loops_needed = math.ceil(total_duration_ms / len(fond_asset))
    bed: AudioSegment = fond_asset * loops_needed   # loop by multiplication
    bed = bed[:total_duration_ms]                   # trim to exact length
    bed = bed + duck_db                             # duck gain
    return bed


# ─────────────────────────────────────────────────────────────────────────────
# 4. assemble_bulletin
# ─────────────────────────────────────────────────────────────────────────────

def assemble_bulletin(
    voice_clip_paths: list[str | Path],
    config_path: str | Path,
    output_path: str | Path,
    *,
    # Optional asset injection for unit-testing (avoids real mp3 on disk)
    intro_asset: AudioSegment | None = None,
    outro_asset: AudioSegment | None = None,
    fond_asset: AudioSegment | None = None,
    transition_asset: AudioSegment | None = None,
) -> AssemblyResult:
    """
    Full bulletin assembly pipeline.

    Pipeline
    --------
    1. Load ``source_bank.json`` → :class:`MixConfig`.
    2. Load/receive intro, outro, fond, transition assets.
    3. Concatenate all *voice_clip_paths* into a single voice track.
    4. :func:`insert_transitions` – overlay transition jingles on every silence.
    5. :func:`build_bed` – create a continuous ducked background exactly as long
       as the voice track (with transitions).
    6. Mix: bed **underneath** voice+transitions (``bed.overlay(voice)``).
    7. Crossfade intro (1 000 ms) → mixed vocal track → crossfade outro (1 000 ms).
    8. Export as stereo MP3 @ 192 kbps.

    The keyword arguments ``*_asset`` allow injecting synthetic
    :class:`~pydub.AudioSegment` objects in tests instead of real files.

    Returns
    -------
    :class:`AssemblyResult` with output_path, transitions_count, duration_ms.
    """
    cfg = MixConfig.from_json(config_path)
    config_data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    roles = config_data.get("roles", {})

    # Backend root is two levels above config/source_bank.json
    backend_root = Path(config_path).parent.parent

    def _load(asset: AudioSegment | None, role: str) -> AudioSegment:
        if asset is not None:
            return asset
        rel_path: str = roles[role]["path"]
        return AudioSegment.from_file(backend_root / rel_path)

    intro = _load(intro_asset, "intro")
    outro = _load(outro_asset, "outro")
    fond = _load(fond_asset, "fond")
    transition = _load(transition_asset, "transition")

    # ── Concatenate voice clips ───────────────────────────────────────────────
    if not voice_clip_paths:
        raise ValueError("At least one voice clip path is required")

    voice_track: AudioSegment = AudioSegment.empty()
    for p in voice_clip_paths:
        voice_track = voice_track + AudioSegment.from_file(p)

    # ── Insert transitions ────────────────────────────────────────────────────
    voice_with_trans, inserted_transitions = insert_transitions(voice_track, transition, cfg)

    # ── Build bed (same length as the voice+transitions track) ────────────────
    bed = build_bed(fond, len(voice_with_trans), cfg.duck_db)

    # ── Mix: bed underneath, voice on top ─────────────────────────────────────
    mixed: AudioSegment = bed.overlay(voice_with_trans)

    # ── Crossfade intro → mixed → outro ──────────────────────────────────────
    #   append(other, crossfade=N) overlaps last N ms of self with first N ms of other
    CROSSFADE_MS = 1_000
    result: AudioSegment = intro.append(mixed, crossfade=CROSSFADE_MS)
    result = result.append(outro, crossfade=CROSSFADE_MS)

    # ── Ensure stereo ─────────────────────────────────────────────────────────
    result = result.set_channels(2)

    # ── Export ────────────────────────────────────────────────────────────────
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.export(str(out), format="mp3", bitrate="192k")

    return AssemblyResult(
        output_path=out,
        transitions_count=len(inserted_transitions),
        duration_ms=len(result),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. loudness_normalize
# ─────────────────────────────────────────────────────────────────────────────

def loudness_normalize(
    input_path: str | Path,
    output_path: str | Path,
    target_lufs: float = -16.0,
) -> Path:
    """
    Normalise the integrated loudness of an audio file to *target_lufs* LUFS.

    Uses **ffmpeg**'s ``loudnorm`` filter (EBU R128 / ITU-R BS.1770-4).
    Single-pass mode is used, which is adequate for broadcast mastering.

    Parameters
    ----------
    input_path:
        Source audio file (any format supported by ffmpeg).
    output_path:
        Destination path; parent directories are created automatically.
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
