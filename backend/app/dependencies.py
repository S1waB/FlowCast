"""
FlowCast – Shared upload-validation dependency.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

# ── Allowed audio formats ─────────────────────────────────────────────────────
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav"})

# ── Size limits ───────────────────────────────────────────────────────────────
MAX_ASSET_BYTES: int = 50 * 1024 * 1024   # 50 MB – source-bank assets
MAX_CLIP_BYTES: int = 500 * 1024 * 1024   # 500 MB – raw vocal clips


async def read_audio_upload(
    file: UploadFile,
    max_bytes: int,
    field_name: str = "file",
) -> tuple[bytes, str]:
    """
    Read and validate an uploaded audio file.

    Checks
    ------
    * Extension is ``.mp3`` or ``.wav``.
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
                f"[{field_name}] Invalid file extension '{ext}'. "
                f"Accepted formats: mp3, wav."
            ),
        )

    content: bytes = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code=422,
            detail=f"[{field_name}] Uploaded file '{filename}' is empty.",
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
