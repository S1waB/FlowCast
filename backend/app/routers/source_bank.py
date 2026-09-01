"""
FlowCast – Source-bank endpoints.

Routes
------
POST   /source-bank/{role}   Upload / replace an audio asset.
GET    /source-bank           List current config + per-asset metadata.
PATCH  /source-bank/config    Edit mixing defaults without redeploying.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from pydub import AudioSegment

from app.core.config import settings
from app.dependencies import MAX_ASSET_BYTES, read_audio_upload
from app.schemas import (
    INTRO_OUTRO_MAX_MS,
    INTRO_OUTRO_MIN_MS,
    VALID_ROLES,
    AssetMetadata,
    AssetUploadResponse,
    ConfigPatchRequest,
    ConfigPatchResponse,
    SourceBankDefaults,
    SourceBankResponse,
)

router = APIRouter(prefix="/source-bank", tags=["Source Bank"])

# One process-level lock to serialise reads/writes to source_bank.json
_json_lock = threading.Lock()

# Mapping from ConfigPatchRequest field names → source_bank.json "defaults" keys
_PATCH_KEY_MAP: dict[str, str] = {
    "duck_db": "duck_db",
    "transition_max_ms": "transition_max_ms",
    "fade_in_ms": "transition_fade_in_ms",
    "fade_out_ms": "transition_fade_out_ms",
    "silence_thresh_db": "silence_thresh_db_relative",
    "min_silence_len_ms": "min_silence_len_ms",
    "min_gap_safety_ms": "min_gap_safety_ms",
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_config() -> dict[str, Any]:
    return json.loads(settings.source_bank_config.read_text(encoding="utf-8"))


def _write_config(data: dict[str, Any]) -> None:
    """Atomic write: temp file then rename to avoid corrupt reads."""
    tmp = settings.source_bank_config.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(settings.source_bank_config)


def _asset_path(role: str, ext: str) -> Path:
    return settings.source_bank_dir / f"{role}{ext}"


def _probe_asset(asset_path: Path, role: str) -> AssetMetadata:
    """Build AssetMetadata for one role by probing the file on disk."""
    if not asset_path.exists():
        return AssetMetadata(role=role, path=str(asset_path), exists=False)

    size_bytes = asset_path.stat().st_size
    duration_ms: int | None = None
    duration_s: float | None = None

    try:
        audio = AudioSegment.from_file(str(asset_path))
        duration_ms = len(audio)
        duration_s = round(duration_ms / 1_000, 2)
    except Exception:
        pass  # corrupt or unsupported – report exists but no duration

    warning: str | None = None
    if role in ("intro", "outro") and duration_ms is not None:
        if duration_ms < INTRO_OUTRO_MIN_MS:
            warning = (
                f"Too short ({duration_s}s < {INTRO_OUTRO_MIN_MS // 1000}s). "
                "Recommended: 4–10 s."
            )
        elif duration_ms > INTRO_OUTRO_MAX_MS:
            warning = (
                f"Too long ({duration_s}s > {INTRO_OUTRO_MAX_MS // 1000}s). "
                "Recommended: 4–10 s."
            )

    return AssetMetadata(
        role=role,
        path=str(asset_path),
        exists=True,
        size_bytes=size_bytes,
        duration_ms=duration_ms,
        duration_s=duration_s,
        duration_warning=warning,
    )


def _defaults_from_config(cfg: dict[str, Any]) -> SourceBankDefaults:
    d = cfg.get("defaults", {})
    return SourceBankDefaults(
        duck_db=d["duck_db"],
        transition_max_ms=d["transition_max_ms"],
        transition_fade_in_ms=d["transition_fade_in_ms"],
        transition_fade_out_ms=d["transition_fade_out_ms"],
        silence_thresh_db_relative=d["silence_thresh_db_relative"],
        min_silence_len_ms=d["min_silence_len_ms"],
        min_gap_safety_ms=d["min_gap_safety_ms"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /source-bank/{role}
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{role}",
    response_model=AssetUploadResponse,
    status_code=201,
    summary="Upload or replace a source-bank asset",
)
async def upload_asset(role: str, file: UploadFile) -> AssetUploadResponse:
    """
    Upload a new **intro**, **outro**, **fond** or **transition** file.

    * Accepted formats: `mp3`, `wav`
    * Maximum size: 50 MB
    * Replaces any previously existing file for that role
    * Updates `source_bank.json` with the new relative path
    """
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown role '{role}'. "
                f"Valid roles: {sorted(VALID_ROLES)}."
            ),
        )

    content, ext = await read_audio_upload(file, MAX_ASSET_BYTES, field_name=role)

    # ── Determine target path ─────────────────────────────────────────────────
    target = _asset_path(role, ext)

    # Remove old file for this role if it has a different extension
    for old_ext in (".mp3", ".wav"):
        old_path = _asset_path(role, old_ext)
        if old_path != target and old_path.exists():
            old_path.unlink(missing_ok=True)

    # ── Write file ────────────────────────────────────────────────────────────
    settings.source_bank_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    # ── Probe duration ────────────────────────────────────────────────────────
    try:
        audio = AudioSegment.from_file(str(target))
        duration_ms = len(audio)
        duration_s = round(duration_ms / 1_000, 2)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Uploaded file could not be decoded as audio: {exc}. "
                "Ensure it is a valid mp3 or wav file."
            ),
        ) from exc

    # ── Update source_bank.json ───────────────────────────────────────────────
    rel_path = f"source_bank/{role}{ext}"
    with _json_lock:
        cfg = _read_config()
        cfg.setdefault("roles", {}).setdefault(role, {})
        cfg["roles"][role]["path"] = rel_path
        _write_config(cfg)

    # ── Duration warning ──────────────────────────────────────────────────────
    warning: str | None = None
    if role in ("intro", "outro"):
        if duration_ms < INTRO_OUTRO_MIN_MS:
            warning = f"Too short ({duration_s}s < 4s). Recommended: 4–10 s."
        elif duration_ms > INTRO_OUTRO_MAX_MS:
            warning = f"Too long ({duration_s}s > 10s). Recommended: 4–10 s."

    return AssetUploadResponse(
        role=role,
        path=rel_path,
        size_bytes=len(content),
        duration_ms=duration_ms,
        duration_s=duration_s,
        duration_warning=warning,
        message=f"Asset '{role}' uploaded successfully ({duration_s}s).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /source-bank
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SourceBankResponse,
    summary="Current source-bank config and asset metadata",
)
def get_source_bank() -> SourceBankResponse:
    """
    Return the full source-bank configuration with per-asset file metadata:

    * Whether the file exists on disk
    * File size (bytes)
    * Duration (ms and seconds)
    * Duration warning for intro/outro (recommended 4–10 s)
    """
    with _json_lock:
        cfg = _read_config()

    roles_cfg: dict[str, Any] = cfg.get("roles", {})
    roles_meta: dict[str, AssetMetadata] = {}

    for role in VALID_ROLES:
        role_data = roles_cfg.get(role, {})
        rel_path: str = role_data.get("path", f"source_bank/{role}.mp3")
        backend_root = settings.source_bank_config.parent.parent
        asset_path = backend_root / rel_path
        roles_meta[role] = _probe_asset(asset_path, role)

    return SourceBankResponse(
        roles=roles_meta,
        defaults=_defaults_from_config(cfg),
    )


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /source-bank/config
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/config",
    response_model=ConfigPatchResponse,
    summary="Edit mixing defaults without redeployment",
)
def patch_config(body: ConfigPatchRequest) -> ConfigPatchResponse:
    """
    Partially update the mixing defaults stored in `source_bank.json`.

    Only supplied fields are modified; omitted fields are left unchanged.
    Changes take effect for the **next** bulletin assembled after this call —
    no restart required.

    | Request field        | JSON key                   |
    |----------------------|----------------------------|
    | `duck_db`            | `duck_db`                  |
    | `transition_max_ms`  | `transition_max_ms`        |
    | `fade_in_ms`         | `transition_fade_in_ms`    |
    | `fade_out_ms`        | `transition_fade_out_ms`   |
    | `silence_thresh_db`  | `silence_thresh_db_relative` |
    | `min_silence_len_ms` | `min_silence_len_ms`       |
    | `min_gap_safety_ms`  | `min_gap_safety_ms`        |
    """
    patch_dict = body.model_dump(exclude_none=True)
    if not patch_dict:
        raise HTTPException(
            status_code=422,
            detail="Request body must include at least one field to update.",
        )

    with _json_lock:
        cfg = _read_config()
        defaults = cfg.setdefault("defaults", {})

        updated: list[str] = []
        for req_key, value in patch_dict.items():
            json_key = _PATCH_KEY_MAP[req_key]
            defaults[json_key] = value
            updated.append(json_key)

        _write_config(cfg)

    return ConfigPatchResponse(
        message=f"Updated {len(updated)} parameter(s): {', '.join(updated)}.",
        defaults=_defaults_from_config(cfg),
    )
