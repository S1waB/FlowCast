"""
FlowCast – Bulletin endpoints.

Routes
------
POST  /bulletins                Upload N vocal clips, launch assembly in background.
GET   /bulletins/{job_id}       Job status + transitions count + final duration.
GET   /bulletins/{job_id}/download  Stream the finished MP3.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import job_store
from app.audio_engine import assemble_bulletin
from app.core.config import settings
from app.dependencies import MAX_CLIP_BYTES, read_audio_upload
from app.schemas import (
    BulletinCreateResponse,
    BulletinStatusResponse,
    JobStatus,
)

router = APIRouter(prefix="/bulletins", tags=["Bulletins"])


# ─────────────────────────────────────────────────────────────────────────────
# Background worker
# ─────────────────────────────────────────────────────────────────────────────

def _sync_assemble(job_id: str) -> None:
    """
    Synchronous assembly worker — runs in a ThreadPoolExecutor so it does not
    block the asyncio event loop.

    Updates the job store as it progresses through pending → processing → done
    (or error).
    """
    job = job_store.get_job(job_id)
    if job is None:
        return

    job_store.update_job(job_id, status=JobStatus.PROCESSING)

    output_path = settings.output_dir / f"{job_id}.mp3"

    try:
        result = assemble_bulletin(
            voice_clip_paths=job.voice_clip_paths,
            config_path=settings.source_bank_config,
            output_path=output_path,
        )
        job_store.update_job(
            job_id,
            status=JobStatus.DONE,
            output_path=str(result.output_path),
            transitions_count=result.transitions_count,
            duration_ms=result.duration_ms,
        )

    except FileNotFoundError as exc:
        # A source-bank asset is missing
        job_store.update_job(
            job_id,
            status=JobStatus.ERROR,
            error=(
                f"Missing source-bank asset: {exc}. "
                "Upload it via POST /source-bank/{role} first."
            ),
        )

    except subprocess.CalledProcessError as exc:
        # ffmpeg failure (loudness normalisation, export, …)
        stderr = (exc.stderr or "")[:800]
        job_store.update_job(
            job_id,
            status=JobStatus.ERROR,
            error=f"ffmpeg failed (exit {exc.returncode}): {stderr}",
        )

    except ValueError as exc:
        job_store.update_job(job_id, status=JobStatus.ERROR, error=str(exc))

    except Exception as exc:  # noqa: BLE001 – broad catch for unknown errors
        job_store.update_job(
            job_id,
            status=JobStatus.ERROR,
            error=f"Unexpected error: {type(exc).__name__}: {exc}",
        )
    finally:
        # Clean up raw clips regardless of outcome
        finished_job = job_store.get_job(job_id)
        if finished_job and finished_job.status != JobStatus.DONE:
            for path in (finished_job.voice_clip_paths or []):
                Path(path).unlink(missing_ok=True)


async def _run_async_assembly(job_id: str) -> None:
    """Wrap the sync worker in a thread pool so the event loop stays free."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_assemble, job_id)


# ─────────────────────────────────────────────────────────────────────────────
# POST /bulletins
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=BulletinCreateResponse,
    status_code=202,
    summary="Upload vocal clips and start bulletin assembly",
)
async def create_bulletin(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
) -> BulletinCreateResponse:
    """
    Accept **one or more** vocal clip uploads (mp3 or wav, max 500 MB each) and
    immediately enqueue bulletin assembly as a background task.

    Returns `job_id` to poll via `GET /bulletins/{job_id}`.

    Assembly pipeline:
    1. Concatenate clips in upload order.
    2. Detect silences → insert transition jingles.
    3. Loop background music (ducked) under the full track.
    4. Crossfade intro → body → outro.
    5. Export stereo MP3 @ 192 kbps.
    """
    if not files:
        raise HTTPException(
            status_code=422,
            detail="At least one vocal clip must be uploaded.",
        )

    # ── Validate & persist each clip ─────────────────────────────────────────
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    # Create the job first so we have a job_id for naming the files
    placeholder_job = job_store.create_job([])
    job_id = placeholder_job.job_id

    saved_paths: list[str] = []
    errors: list[str] = []

    for idx, upload in enumerate(files):
        field_name = f"files[{idx}]"
        try:
            content, ext = await read_audio_upload(
                upload, MAX_CLIP_BYTES, field_name=field_name
            )
        except HTTPException as exc:
            errors.append(exc.detail)
            continue

        clip_path = settings.uploads_dir / f"{job_id}_clip{idx:03d}{ext}"
        clip_path.write_bytes(content)
        saved_paths.append(str(clip_path))

    # If any file failed validation, abort and clean up
    if errors:
        for p in saved_paths:
            Path(p).unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail={"message": "One or more clips failed validation.", "errors": errors},
        )

    # ── Update job with real paths and launch worker ──────────────────────────
    job_store.update_job(
        job_id,
        voice_clip_paths=saved_paths,
        clip_count=len(saved_paths),
    )

    background_tasks.add_task(_run_async_assembly, job_id)

    return BulletinCreateResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        clip_count=len(saved_paths),
        message=(
            f"Job {job_id} accepted. "
            f"{len(saved_paths)} clip(s) queued for assembly. "
            f"Poll GET /bulletins/{job_id} for status."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /bulletins/{job_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{job_id}",
    response_model=BulletinStatusResponse,
    summary="Get bulletin job status",
)
def get_bulletin_status(job_id: str) -> BulletinStatusResponse:
    """
    Return the current status of a bulletin assembly job.

    | Status       | Meaning                              |
    |--------------|--------------------------------------|
    | `pending`    | Job accepted, not yet started        |
    | `processing` | Assembly in progress                 |
    | `done`       | MP3 ready – download via `.../download` |
    | `error`      | Assembly failed – see `error` field  |

    Once `done`, `transitions_count` and `duration_ms`/`duration_s` are populated.
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found.",
        )

    duration_s: float | None = (
        round(job.duration_ms / 1_000, 2) if job.duration_ms is not None else None
    )

    return BulletinStatusResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        clip_count=job.clip_count,
        transitions_count=job.transitions_count,
        duration_ms=job.duration_ms,
        duration_s=duration_s,
        error=job.error,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /bulletins/{job_id}/download
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{job_id}/download",
    summary="Stream the finished bulletin MP3",
    response_class=FileResponse,
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "MP3 audio stream"},
        404: {"description": "Job not found"},
        409: {"description": "Bulletin not ready yet"},
    },
)
def download_bulletin(job_id: str) -> FileResponse:
    """
    Stream the finished MP3 bulletin.

    Only available when `status == done`.
    Returns `409 Conflict` if the job is still pending or processing,
    and re-surfaces the error message if `status == error`.
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    if job.status == JobStatus.ERROR:
        raise HTTPException(
            status_code=500,
            detail=f"Job '{job_id}' failed: {job.error}",
        )

    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Bulletin not ready yet (status: {job.status.value}). "
                f"Try again later."
            ),
        )

    output_path = Path(job.output_path)  # type: ignore[arg-type]
    if not output_path.exists():
        raise HTTPException(
            status_code=500,
            detail="Output file missing from disk even though job reported success.",
        )

    return FileResponse(
        path=str(output_path),
        media_type="audio/mpeg",
        filename=f"bulletin_{job_id}.mp3",
        headers={"Content-Disposition": f'attachment; filename="bulletin_{job_id}.mp3"'},
    )
