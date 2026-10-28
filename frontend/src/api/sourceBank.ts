/**
 * Source Bank API client
 */

const API_BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const getUrl = (path: string) => import.meta.env.DEV ? `/api${path}` : `${API_BASE}${path}`;

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
  transition_high_db: number;
  transition_total_ms: number;
  transition_fade_in_ms: number;
  transition_fade_out_ms: number;
  silence_thresh_db_relative: number;
  min_silence_len_ms: number;
  segment_trim_pad_ms: number;
  normalize_voice?: boolean;
  target_peak_dbfs?: number;
}

export interface SourceBankResponse {
  roles: Record<string, AssetMetadata>;
  defaults: SourceBankDefaults;
}

export interface ConfigPatchRequest {
  duck_db?: number;
  transition_high_db?: number;
  transition_total_ms?: number;
  transition_fade_in_ms?: number;
  transition_fade_out_ms?: number;
  silence_thresh_db_relative?: number;
  min_silence_len_ms?: number;
  segment_trim_pad_ms?: number;
  normalize_voice?: boolean;
  target_peak_dbfs?: number;
}

export interface ConfigPatchResponse {
  message: string;
  defaults: SourceBankDefaults;
}

export interface AssetUploadResponse {
  role: string;
  path: string;
  size_bytes: number;
  duration_ms: number;
  duration_s: number;
  duration_warning?: string;
  message: string;
}

// We use the Vite proxy during local dev, or the direct URL
export async function fetchSourceBank(): Promise<SourceBankResponse> {
  const res = await fetch(getUrl("/source-bank"));
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to fetch source bank");
  }
  return res.json() as Promise<SourceBankResponse>;
}

export async function updateSourceBankConfig(config: ConfigPatchRequest): Promise<ConfigPatchResponse> {
  const res = await fetch(getUrl("/source-bank/config"), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to update config");
  }
  return res.json() as Promise<ConfigPatchResponse>;
}

export async function uploadAsset(role: string, file: File): Promise<AssetUploadResponse> {
  const formData = new FormData();
  formData.append("file", file); // Match backend single file upload
  const res = await fetch(getUrl(`/source-bank/${role}`), {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to upload asset");
  }
  return res.json() as Promise<AssetUploadResponse>;
}
