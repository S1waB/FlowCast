"""
Unit tests for Source Bank Projects (Presets) router functions.
"""

from __future__ import annotations

import pytest
from app.routers.projects import (
    activate_project,
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from app.schemas import ProjectCreateRequest, ProjectUpdateRequest


def test_list_projects():
    data = list_projects()
    assert data.active_project_id is not None
    assert len(data.projects) >= 1
    default_proj = data.projects[0]
    assert default_proj.id == "default" or default_proj.name == "Projet Standard"


def test_create_update_activate_delete_project():
    # 1. Create a project
    req = ProjectCreateRequest(
        name="Radio Matin",
        description="Jingles et ducking pour la matinale",
        copy_current_bank=True,
    )
    proj = create_project(req)
    assert proj.name == "Radio Matin"
    proj_id = proj.id

    # 2. Get project details
    fetched = get_project(proj_id)
    assert fetched.id == proj_id
    assert fetched.name == "Radio Matin"

    # 3. List projects should now include it
    data = list_projects()
    assert any(p.id == proj_id for p in data.projects)

    # 4. Update project
    up_req = ProjectUpdateRequest(
        name="Radio Matin Pro",
        description="Mise a jour matinale",
        config={"duck_db": -24.0},
    )
    updated = update_project(proj_id, up_req)
    assert updated.name == "Radio Matin Pro"
    assert updated.config.get("duck_db") == -24.0

    # 5. Activate project
    act_res = activate_project(proj_id)
    assert act_res["active_project_id"] == proj_id

    # 6. Delete project
    del_res = delete_project(proj_id)
    assert del_res["active_project_id"] != proj_id
    # Ensure it is removed
    data_after = list_projects()
    assert not any(p.id == proj_id for p in data_after.projects)
