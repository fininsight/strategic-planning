const ANALYSIS_API_BASE_URL = (import.meta.env.VITE_ANALYSIS_API_BASE_URL ?? "").replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${ANALYSIS_API_BASE_URL}${path}`;
}

export function assetUrl(path: string): string {
  if (!path || /^(https?:)?\/\//.test(path) || path.startsWith("data:") || path.startsWith("blob:")) {
    return path;
  }
  if (!path.startsWith("/api/")) {
    return path;
  }
  return apiUrl(path);
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  if (!contentType.includes("application/json")) {
    throw new Error(`Expected JSON response from ${url}`);
  }
  return (await response.json()) as T;
}
