/**
 * Projects (Bank Presets) API client
 */

const API_BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const getUrl = (path: string) => (import.meta.env.DEV ? `/api${path}` : `${API_BASE}${path}`);

export interface ProjectModel {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  config: Record<string, any>;
  assets: Record<string, string>;
}

export interface ProjectListResponse {
  active_project_id: string;
  projects: ProjectModel[];
}

export interface ProjectCreateRequest {
  name: string;
  description?: string;
  copy_current_bank?: boolean;
}

export interface ProjectUpdateRequest {
  name?: string;
  description?: string;
  config?: Record<string, any>;
  save_current_bank?: boolean;
}

export async function fetchProjects(): Promise<ProjectListResponse> {
  const res = await fetch(getUrl("/projects"));
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to fetch projects");
  }
  return res.json() as Promise<ProjectListResponse>;
}

export async function createProject(data: ProjectCreateRequest): Promise<ProjectModel> {
  const res = await fetch(getUrl("/projects"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to create project");
  }
  return res.json() as Promise<ProjectModel>;
}

export async function activateProject(projectId: string): Promise<{ message: string; active_project_id: string }> {
  const res = await fetch(getUrl(`/projects/${projectId}/activate`), {
    method: "POST",
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to activate project");
  }
  return res.json();
}

export async function updateProject(projectId: string, data: ProjectUpdateRequest): Promise<ProjectModel> {
  const res = await fetch(getUrl(`/projects/${projectId}`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to update project");
  }
  return res.json() as Promise<ProjectModel>;
}

export async function deleteProject(projectId: string): Promise<{ message: string; active_project_id: string }> {
  const res = await fetch(getUrl(`/projects/${projectId}`), {
    method: "DELETE",
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to delete project");
  }
  return res.json();
}

