"""
FlowCast – Bulletin endpoints.

Routes
------
POST  /bulletins                 Upload ONE raw vocal mp3, detect segments, start assembly.
GET   /bulletins/{job_id}        Job status + segments/transitions count + final duration.
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
from app.dependencies import (
    CONVERT_TO_MP3_EXTENSIONS,
    MAX_CLIP_BYTES,
    convert_to_mp3,
    read_audio_upload,
)
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
    Synchronous assembly worker — runs in a ThreadPoolExecutor.

    Updates the job store: pending → processing → done | error.
    """
    job = job_store.get_job(job_id)
    if job is None:
        return

    job_store.update_job(job_id, status=JobStatus.PROCESSING)

    output_path = settings.output_dir / f"{job_id}.mp3"

    try:
        result = assemble_bulletin(
            raw_audio_path=job.voice_clip_paths[0],  # single file per spec
            config_path=settings.source_bank_config,
            output_path=output_path,
        )
        job_store.update_job(
            job_id,
            status=JobStatus.DONE,
            output_path=str(result.output_path),
            segments_count=result.segments_count,
            transitions_count=result.transitions_count,
            duration_ms=result.duration_ms,
        )

    except FileNotFoundError as exc:
        job_store.update_job(
            job_id,
            status=JobStatus.ERROR,
            error=(
                f"Missing source-bank asset: {exc}. "
                "Upload it via POST /source-bank/{role} first."
            ),
        )

    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "")[:800]
        job_store.update_job(
            job_id,
            status=JobStatus.ERROR,
            error=f"ffmpeg failed (exit {exc.returncode}): {stderr}",
        )

    except ValueError as exc:
        job_store.update_job(job_id, status=JobStatus.ERROR, error=str(exc))

    except Exception as exc:  # noqa: BLE001
        job_store.update_job(
            job_id,
            status=JobStatus.ERROR,
            error=f"Unexpected error: {type(exc).__name__}: {exc}",
        )
    finally:
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
    summary="Upload a raw vocal audio file and start bulletin assembly",
)
async def create_bulletin(
    file: UploadFile,
    background_tasks: BackgroundTasks,
) -> BulletinCreateResponse:
    """
    Accept **one** raw vocal audio file (mp3 or wav, max 500 MB) and immediately
    enqueue bulletin assembly as a background task.

    The assembly pipeline:
    1. Detect silences → split into speech segments automatically.
    2. Trim each segment's edges individually.
    3. Build continuous fond track with gain envelope (duck/high/duck).
    4. Mix segments + transitions (fond-based, 3 000 ms each) + intro + outro.
    5. Export stereo MP3 @ 192 kbps.

    Returns `job_id` to poll via `GET /bulletins/{job_id}`.
    """
    # ── Validate & persist the raw audio file ────────────────────────────────
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    placeholder_job = job_store.create_job([])
    job_id = placeholder_job.job_id

    content, ext = await read_audio_upload(file, MAX_CLIP_BYTES, field_name="file")

    if ext in CONVERT_TO_MP3_EXTENSIONS:
        temp_input = settings.uploads_dir / f"{job_id}_uploaded{ext}"
        clip_path = settings.uploads_dir / f"{job_id}_raw.mp3"
        try:
            temp_input.write_bytes(content)
            convert_to_mp3(temp_input, clip_path)
        except Exception as exc:
            temp_input.unlink(missing_ok=True)
            clip_path.unlink(missing_ok=True)
            job_store.update_job(
                job_id,
                status=JobStatus.ERROR,
                error=f"Erreur de conversion en MP3: {exc}",
            )
            raise HTTPException(
                status_code=422,
                detail=f"Impossible de convertir le fichier audio/vidéo en MP3: {exc}",
            ) from exc
        finally:
            temp_input.unlink(missing_ok=True)
    else:
        clip_path = settings.uploads_dir / f"{job_id}_raw{ext}"
        clip_path.write_bytes(content)

    # ── Update job with real path and launch worker ───────────────────────────
    job_store.update_job(
        job_id,
        voice_clip_paths=[str(clip_path)],
    )

    background_tasks.add_task(_run_async_assembly, job_id)

    return BulletinCreateResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=(
            f"Job {job_id} accepted. "
            f"Raw audio queued for segment detection and assembly. "
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

    | Status       | Meaning                                  |
    |--------------|------------------------------------------|
    | `pending`    | Job accepted, not yet started            |
    | `processing` | Assembly in progress                     |
    | `done`       | MP3 ready – download via `.../download`  |
    | `error`      | Assembly failed – see `error` field      |

    Once `done`, `segments_count`, `transitions_count`, and `duration_ms` are populated.
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
        segments_count=job.segments_count,
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
    Returns `409 Conflict` if the job is still pending or processing.
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
                "Try again later."
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
