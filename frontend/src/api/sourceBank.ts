/**
 * Source Bank API client
 */

export interface AssetMetadata {
  role: string;
  path: string;
  exists: boolean;
  size_bytes?: number;
  duration_ms?: number;
  duration_s?: number;
  duration_warning?: string;
}

export interface SourceBankDefaults {
  duck_db: number;
  transition_max_ms: number;
  transition_fade_in_ms: number;
  transition_fade_out_ms: number;
  silence_thresh_db_relative: number;
  min_silence_len_ms: number;
  min_gap_safety_ms: number;
}

export interface SourceBankResponse {
  roles: Record<string, AssetMetadata>;
  defaults: SourceBankDefaults;
}

export interface ConfigPatchRequest {
  duck_db?: number;
  transition_max_ms?: number;
  fade_in_ms?: number;
  fade_out_ms?: number;
  silence_thresh_db?: number;
  min_silence_len_ms?: number;
  min_gap_safety_ms?: number;
}

// We use the Vite proxy during local dev, or the direct URL
const API_BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const getUrl = (path: string) => import.meta.env.DEV ? `/api${path}` : `${API_BASE}${path}`;

export async function fetchSourceBank(): Promise<SourceBankResponse> {
  const res = await fetch(getUrl("/source-bank"));
  if (!res.ok) throw new Error("Failed to fetch source bank");
  return res.json();
}

export async function updateSourceBankConfig(data: ConfigPatchRequest): Promise<any> {
  const res = await fetch(getUrl("/source-bank/config"), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to update config");
  }
  return res.json();
}

export async function uploadAsset(role: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append("file", file); // The FastAPI endpoint expects "file"
  
  const res = await fetch(getUrl(`/source-bank/${role}`), {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const error = await res.json();
    // Sometimes detail is an array for validation errors
    const detail = Array.isArray(error.detail) ? error.detail[0]?.msg : error.detail;
    throw new Error(detail || `Failed to upload ${role}`);
  }
  return res.json();
}
