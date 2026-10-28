"""
FlowCast – Projects (Bank Presets) Router.
Allows saving, loading, updating, and deleting named configurations and assets in the Source Bank.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from app.core.config import settings
from app.dependencies import (
    CONVERT_TO_MP3_EXTENSIONS,
    MAX_ASSET_BYTES,
    convert_to_mp3,
    read_audio_upload,
)
from app.schemas import (
    VALID_ROLES,
    AssetUploadResponse,
    INTRO_OUTRO_MAX_MS,
    INTRO_OUTRO_MIN_MS,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectModel,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/projects", tags=["Projects"])

_projects_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _projects_file() -> Path:
    return settings.config_dir / "projects.json"


def _projects_asset_dir() -> Path:
    p = settings.source_bank_dir / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_bank_config() -> dict[str, Any]:
    if not settings.source_bank_config.exists():
        return {}
    return json.loads(settings.source_bank_config.read_text(encoding="utf-8"))


def _write_bank_config(cfg: dict[str, Any]) -> None:
    tmp = settings.source_bank_config.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(settings.source_bank_config)


def _init_projects_data() -> dict[str, Any]:
    """Create default projects.json from current bank state."""
    current_cfg = _read_bank_config()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Extract default config fields
    config_keys = [
        "duck_db", "transition_high_db", "transition_total_ms",
        "transition_fade_in_ms", "transition_fade_out_ms",
        "silence_thresh_db_relative", "min_silence_len_ms",
        "segment_trim_pad_ms", "normalize_voice", "target_peak_dbfs",
        "strip_edge_silence", "enhance_voice",
    ]
    defaults_cfg = {k: current_cfg.get(k) for k in config_keys if k in current_cfg}
    if not defaults_cfg:
        defaults_cfg = {
            "duck_db": -26.0,
            "transition_high_db": -3.0,
            "transition_total_ms": 3000,
            "transition_fade_in_ms": 1000,
            "transition_fade_out_ms": 1000,
            "silence_thresh_db_relative": -16.0,
            "min_silence_len_ms": 400,
            "segment_trim_pad_ms": 0,
            "normalize_voice": True,
            "target_peak_dbfs": -1.0,
            "strip_edge_silence": True,
            "enhance_voice": True,
        }

    default_assets = {
        "intro": current_cfg.get("intro", "source_bank/intro.mp3"),
        "outro": current_cfg.get("outro", "source_bank/outro.mp3"),
        "fond": current_cfg.get("fond", "source_bank/fond.mp3"),
    }

    default_project = {
        "id": "default",
        "name": "Projet Standard",
        "description": "Configuration standard et assets de base de FlowCast",
        "created_at": now_iso,
        "updated_at": now_iso,
        "config": defaults_cfg,
        "assets": default_assets,
    }

    return {
        "active_project_id": "default",
        "projects": [default_project],
    }


def _read_projects_data() -> dict[str, Any]:
    f = _projects_file()
    if not f.exists():
        data = _init_projects_data()
        _write_projects_data(data)
        return data

    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if "projects" not in data or not data["projects"]:
            data = _init_projects_data()
            _write_projects_data(data)
        return data
    except Exception:
        data = _init_projects_data()
        _write_projects_data(data)
        return data


def _write_projects_data(data: dict[str, Any]) -> None:
    f = _projects_file()
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def _apply_project_to_bank(project: dict[str, Any]) -> None:
    """Apply a project's parameters and assets directly into source_bank.json."""
    cfg = _read_bank_config()

    # Apply mixing parameters
    for k, v in project.get("config", {}).items():
        cfg[k] = v

    # Apply asset paths
    for role, rel_path in project.get("assets", {}).items():
        if role in VALID_ROLES:
            cfg[role] = rel_path

    _write_bank_config(cfg)


def _sync_bank_into_project(project: dict[str, Any]) -> None:
    """Capture current active bank settings and assets into project."""
    cfg = _read_bank_config()
    config_keys = [
        "duck_db", "transition_high_db", "transition_total_ms",
        "transition_fade_in_ms", "transition_fade_out_ms",
        "silence_thresh_db_relative", "min_silence_len_ms",
        "segment_trim_pad_ms", "normalize_voice", "target_peak_dbfs",
        "strip_edge_silence", "enhance_voice",
    ]
    for k in config_keys:
        if k in cfg:
            project.setdefault("config", {})[k] = cfg[k]

    for role in VALID_ROLES:
        if role in cfg:
            project.setdefault("assets", {})[role] = cfg[role]

    project["updated_at"] = datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse, summary="List all saved projects")
def list_projects() -> ProjectListResponse:
    with _projects_lock:
        data = _read_projects_data()
        active_id = data.get("active_project_id", "default")
        projects = []
        for p in data.get("projects", []):
            projects.append(
                ProjectModel(
                    id=p["id"],
                    name=p["name"],
                    description=p.get("description", ""),
                    is_active=(p["id"] == active_id),
                    created_at=p.get("created_at", ""),
                    updated_at=p.get("updated_at", ""),
                    config=p.get("config", {}),
                    assets=p.get("assets", {}),
                )
            )
        return ProjectListResponse(
            active_project_id=active_id,
            projects=projects,
        )


@router.post("", response_model=ProjectModel, status_code=201, summary="Create a new project")
def create_project(body: ProjectCreateRequest) -> ProjectModel:
    with _projects_lock:
        data = _read_projects_data()

        # Generate id
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", body.name.lower().strip())
        slug = re.sub(r"_+", "_", slug).strip("_")
        if not slug:
            slug = "project"
        proj_id = f"{slug}_{uuid.uuid4().hex[:6]}"

        now_iso = datetime.now(timezone.utc).isoformat()
        proj_assets_dir = _projects_asset_dir() / proj_id
        proj_assets_dir.mkdir(parents=True, exist_ok=True)

        current_cfg = _read_bank_config()
        backend_root = settings.source_bank_config.parent.parent

        # Setup config & copy assets if requested
        if body.copy_current_bank:
            config_keys = [
                "duck_db", "transition_high_db", "transition_total_ms",
                "transition_fade_in_ms", "transition_fade_out_ms",
                "silence_thresh_db_relative", "min_silence_len_ms",
                "segment_trim_pad_ms", "normalize_voice", "target_peak_dbfs",
                "strip_edge_silence", "enhance_voice",
            ]
            proj_config = {k: current_cfg.get(k) for k in config_keys if k in current_cfg}
            proj_assets: dict[str, str] = {}

            # Copy active audio assets into project folder
            for role in VALID_ROLES:
                src_rel = current_cfg.get(role)
                if src_rel:
                    src_path = backend_root / src_rel
                    if src_path.exists():
                        dest_filename = f"{role}{src_path.suffix}"
                        dest_path = proj_assets_dir / dest_filename
                        shutil.copy2(src_path, dest_path)
                        proj_assets[role] = f"source_bank/projects/{proj_id}/{dest_filename}"
                    else:
                        proj_assets[role] = src_rel
                else:
                    proj_assets[role] = f"source_bank/{role}.mp3"
        else:
            proj_config = {
                "duck_db": -26.0,
                "transition_high_db": -3.0,
                "transition_total_ms": 3000,
                "transition_fade_in_ms": 1000,
                "transition_fade_out_ms": 1000,
                "silence_thresh_db_relative": -16.0,
                "min_silence_len_ms": 400,
                "segment_trim_pad_ms": 0,
                "normalize_voice": True,
                "target_peak_dbfs": -1.0,
                "strip_edge_silence": True,
                "enhance_voice": True,
            }
            proj_assets = {
                "intro": f"source_bank/projects/{proj_id}/intro.mp3",
                "outro": f"source_bank/projects/{proj_id}/outro.mp3",
                "fond": f"source_bank/projects/{proj_id}/fond.mp3",
            }

        new_proj = {
            "id": proj_id,
            "name": body.name,
            "description": body.description or "",
            "created_at": now_iso,
            "updated_at": now_iso,
            "config": proj_config,
            "assets": proj_assets,
        }

        data["projects"].append(new_proj)
        data["active_project_id"] = proj_id
        _apply_project_to_bank(new_proj)
        _write_projects_data(data)

        return ProjectModel(
            id=new_proj["id"],
            name=new_proj["name"],
            description=new_proj["description"],
            is_active=True,
            created_at=new_proj["created_at"],
            updated_at=new_proj["updated_at"],
            config=new_proj["config"],
            assets=new_proj["assets"],
        )


@router.get("/{project_id}", response_model=ProjectModel, summary="Get project details")
def get_project(project_id: str) -> ProjectModel:
    with _projects_lock:
        data = _read_projects_data()
        active_id = data.get("active_project_id", "default")
        for p in data.get("projects", []):
            if p["id"] == project_id:
                return ProjectModel(
                    id=p["id"],
                    name=p["name"],
                    description=p.get("description", ""),
                    is_active=(p["id"] == active_id),
                    created_at=p.get("created_at", ""),
                    updated_at=p.get("updated_at", ""),
                    config=p.get("config", {}),
                    assets=p.get("assets", {}),
                )
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")


@router.post("/{project_id}/activate", summary="Activate/load a project into the active source bank")
def activate_project(project_id: str) -> dict[str, Any]:
    with _projects_lock:
        data = _read_projects_data()
        target_proj = None
        for p in data.get("projects", []):
            if p["id"] == project_id:
                target_proj = p
                break

        if not target_proj:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

        data["active_project_id"] = project_id
        _apply_project_to_bank(target_proj)
        _write_projects_data(data)

        return {
            "message": f"Project '{target_proj['name']}' activated successfully.",
            "active_project_id": project_id,
        }


@router.put("/{project_id}", response_model=ProjectModel, summary="Update a project")
def update_project(project_id: str, body: ProjectUpdateRequest) -> ProjectModel:
    with _projects_lock:
        data = _read_projects_data()
        active_id = data.get("active_project_id", "default")
        target_proj = None
        for p in data.get("projects", []):
            if p["id"] == project_id:
                target_proj = p
                break

        if not target_proj:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

        if body.name is not None:
            target_proj["name"] = body.name
        if body.description is not None:
            target_proj["description"] = body.description
        if body.config is not None:
            target_proj.setdefault("config", {}).update(body.config)

        if body.save_current_bank:
            _sync_bank_into_project(target_proj)

        target_proj["updated_at"] = datetime.now(timezone.utc).isoformat()

        # If this is the active project, re-apply to bank
        if active_id == project_id:
            _apply_project_to_bank(target_proj)

        _write_projects_data(data)

        return ProjectModel(
            id=target_proj["id"],
            name=target_proj["name"],
            description=target_proj.get("description", ""),
            is_active=(project_id == active_id),
            created_at=target_proj.get("created_at", ""),
            updated_at=target_proj.get("updated_at", ""),
            config=target_proj.get("config", {}),
            assets=target_proj.get("assets", {}),
        )


@router.delete("/{project_id}", summary="Delete a project")
def delete_project(project_id: str) -> dict[str, Any]:
    with _projects_lock:
        data = _read_projects_data()
        projects = data.get("projects", [])

        if len(projects) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the only remaining project.",
            )

        target_idx = None
        for idx, p in enumerate(projects):
            if p["id"] == project_id:
                target_idx = idx
                break

        if target_idx is None:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

        removed = projects.pop(target_idx)

        # Delete project assets directory if separate
        proj_dir = _projects_asset_dir() / project_id
        if proj_dir.exists():
            shutil.rmtree(proj_dir, ignore_errors=True)

        # If deleted project was active, switch to first project
        if data.get("active_project_id") == project_id:
            data["active_project_id"] = projects[0]["id"]
            _apply_project_to_bank(projects[0])

        _write_projects_data(data)

        return {
            "message": f"Project '{removed['name']}' deleted successfully.",
            "active_project_id": data["active_project_id"],
        }


@router.post(
    "/{project_id}/assets/{role}",
    response_model=AssetUploadResponse,
    status_code=201,
    summary="Upload an audio asset directly to a project",
)
async def upload_project_asset(project_id: str, role: str, file: UploadFile) -> AssetUploadResponse:
    if role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role '{role}'. Valid: {sorted(VALID_ROLES)}.")

    with _projects_lock:
        data = _read_projects_data()
        target_proj = None
        for p in data.get("projects", []):
            if p["id"] == project_id:
                target_proj = p
                break

        if not target_proj:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    content, ext = await read_audio_upload(file, MAX_ASSET_BYTES, field_name=role)
    proj_dir = _projects_asset_dir() / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)

    if ext in CONVERT_TO_MP3_EXTENSIONS:
        final_ext = ".mp3"
        target = proj_dir / f"{role}{final_ext}"
        temp_input = proj_dir / f"{role}_upload{ext}"
        try:
            temp_input.write_bytes(content)
            convert_to_mp3(temp_input, target)
        finally:
            temp_input.unlink(missing_ok=True)
    else:
        final_ext = ext
        target = proj_dir / f"{role}{final_ext}"
        target.write_bytes(content)

    rel_path = f"source_bank/projects/{project_id}/{role}{final_ext}"

    # Probe duration
    from pydub import AudioSegment
    duration_ms = 0
    duration_s = 0.0
    try:
        audio = AudioSegment.from_file(str(target))
        duration_ms = len(audio)
        duration_s = round(duration_ms / 1_000, 2)
    except Exception:
        pass

    with _projects_lock:
        target_proj.setdefault("assets", {})[role] = rel_path
        target_proj["updated_at"] = datetime.now(timezone.utc).isoformat()

        # If active, also update active bank
        if data.get("active_project_id") == project_id:
            _apply_project_to_bank(target_proj)

        _write_projects_data(data)

    warning = None
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
        message=f"Asset '{role}' saved for project '{target_proj['name']}'.",
    )


def get_active_project_name() -> str:
    """Return the name of the currently active project."""
    with _projects_lock:
        data = _read_projects_data()
        active_id = data.get("active_project_id", "default")
        for p in data.get("projects", []):
            if p["id"] == active_id:
                return p.get("name", "default")
        return "default"

