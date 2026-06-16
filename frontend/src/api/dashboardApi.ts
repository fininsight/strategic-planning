import { DashboardPayload } from "../types/notice";
import { normalizeNotice } from "../utils/filters";

export async function loadDashboardData(): Promise<DashboardPayload> {
  const response = await fetch("data/notices.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const payload = (await response.json()) as DashboardPayload;
  return {
    ...payload,
    notices: (payload.notices ?? []).map(normalizeNotice),
  };
}
