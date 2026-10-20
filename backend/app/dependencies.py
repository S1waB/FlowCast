"""
FlowCast – Shared upload-validation dependency and conversion utilities.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pydub import AudioSegment

logger = logging.getLogger("flowcast.dependencies")

# ── Allowed audio/video formats ───────────────────────────────────────────────
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav", ".m4a", ".ma4", ".mp4"})
CONVERT_TO_MP3_EXTENSIONS: frozenset[str] = frozenset({".m4a", ".ma4", ".mp4"})

# ── Size limits ───────────────────────────────────────────────────────────────
MAX_ASSET_BYTES: int = 50 * 1024 * 1024   # 50 MB – source-bank assets
MAX_CLIP_BYTES: int = 500 * 1024 * 1024   # 500 MB – raw vocal clips


def convert_to_mp3(src_path: Path, dest_path: Path) -> Path:
    """
    Convert an audio or video file (e.g. .m4a, .ma4, .mp4, .wav) to .mp3 at 192 kbps.
    Uses ffmpeg with -vn (video disabled) so video files are converted to pure audio.
    Falls back to pydub.AudioSegment if ffmpeg CLI fails.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src_path),
        "-vn",                    # Discard video stream if present
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(dest_path),
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return dest_path
    except Exception as exc:
        logger.warning(
            "ffmpeg CLI conversion failed (%s), attempting pydub fallback...",
            exc,
        )
        try:
            audio = AudioSegment.from_file(str(src_path))
            audio.export(str(dest_path), format="mp3", bitrate="192k")
            return dest_path
        except Exception as pydub_exc:
            raise RuntimeError(
                f"Failed to convert {src_path.name} to MP3: {exc} | {pydub_exc}"
            ) from pydub_exc


async def read_audio_upload(
    file: UploadFile,
    max_bytes: int,
    field_name: str = "file",
) -> tuple[bytes, str]:
    """
    Read and validate an uploaded audio or video file.

    Checks
    ------
    * Extension is in ALLOWED_EXTENSIONS (.mp3, .wav, .m4a, .ma4, .mp4).
    * File is non-empty.
    * File does not exceed *max_bytes*.

    Returns
    -------
    ``(raw_bytes, lower_case_extension)``

    Raises
    ------
    :class:`~fastapi.HTTPException`
        422 – bad extension or empty file.
        413 – file too large.
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"[{field_name}] Extension invalide '{ext}'. "
                f"Formats acceptés: mp3, wav, m4a, ma4, mp4."
            ),
        )

    content: bytes = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code=422,
            detail=f"[{field_name}] Le fichier uploadé '{filename}' est vide.",
        )

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"[{field_name}] File size {len(content):,} B exceeds the "
                f"maximum allowed {max_bytes:,} B "
                f"({max_bytes // (1024 * 1024)} MB)."
            ),
        )

    return content, ext

