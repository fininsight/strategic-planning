const ANALYSIS_API_BASE_URL = (import.meta.env.VITE_ANALYSIS_API_BASE_URL ?? "").replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${ANALYSIS_API_BASE_URL}${path}`;
}

export function assetUrl(path: string): string {
  if (!path || path.startsWith("data:") || path.startsWith("blob:")) {
    return path;
  }
  if (/^https?:\/\//.test(path)) {
    try {
      const url = new URL(path);
      if (url.pathname.startsWith("/api/") && ["localhost", "127.0.0.1"].includes(url.hostname)) {
        return apiUrl(`${url.pathname}${url.search}${url.hash}`);
      }
    } catch {
      return path;
    }
    return path;
  }
  if (path.startsWith("//")) {
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
