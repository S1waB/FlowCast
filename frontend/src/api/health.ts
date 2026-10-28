/**
 * FlowCast Health API helper.
 * Calls GET /health on the FastAPI backend and returns the parsed response.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp: string;
}

const API_BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const getUrl = (path: string) => (import.meta.env.DEV ? `/api${path}` : `${API_BASE}${path}`);

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(getUrl("/health"));
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<HealthResponse>;
}
