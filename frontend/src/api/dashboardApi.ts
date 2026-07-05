import { DashboardPayload } from "../types/notice";
import { normalizeNotice } from "../utils/filters";

export async function loadDashboardData(): Promise<DashboardPayload> {
  const response = await fetch("/api/notices", { cache: "no-store" }).catch(() => undefined);
  const fallbackResponse = response?.ok ? response : await fetch("data/notices.json", { cache: "no-store" });
  if (!fallbackResponse.ok) {
    throw new Error(`HTTP ${fallbackResponse.status}`);
  }

  const payload = (await fallbackResponse.json()) as DashboardPayload;
  return {
    ...payload,
    notices: (payload.notices ?? []).map(normalizeNotice),
  };
}
