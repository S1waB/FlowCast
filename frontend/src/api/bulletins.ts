/**
 * Bulletins API client
 */

const API_BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const getUrl = (path: string) => import.meta.env.DEV ? `/api${path}` : `${API_BASE}${path}`;

export type JobStatus = "pending" | "processing" | "done" | "error";

export interface BulletinCreateResponse {
  job_id: string;
  status: JobStatus;
  segments_count?: number;
  message: string;
}

export interface BulletinStatusResponse {
  job_id: string;
  status: JobStatus;
  created_at: string;
  segments_count?: number;
  transitions_count?: number;
  duration_ms?: number;
  duration_s?: number;
  project_name?: string;
  error?: string;
}

export async function createBulletin(file: File, projectName?: string): Promise<BulletinCreateResponse> {
  const formData = new FormData();
  formData.append("file", file); // Match backend single file upload
  if (projectName) {
    formData.append("project_name", projectName);
  }

  const res = await fetch(getUrl("/bulletins"), {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail?.message || error.detail || "Failed to create bulletin");
  }
  return res.json();
}

export async function getBulletinStatus(jobId: string): Promise<BulletinStatusResponse> {
  const res = await fetch(getUrl(`/bulletins/${jobId}`));
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to fetch bulletin status");
  }
  return res.json();
}

export function getDownloadUrl(jobId: string): string {
  return getUrl(`/bulletins/${jobId}/download`);
}
