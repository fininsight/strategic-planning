import { DashboardPayload } from "../types/notice";
import { normalizeNotice } from "../utils/filters";
import { apiUrl, fetchJson } from "./baseUrl";

export async function loadDashboardData(): Promise<DashboardPayload> {
  const payload = await fetchJson<DashboardPayload>(apiUrl("/api/notices"), { cache: "no-store" }).catch(() =>
    fetchJson<DashboardPayload>("data/notices.json", { cache: "no-store" }),
  );
  return {
    ...payload,
    notices: (payload.notices ?? []).map(normalizeNotice),
  };
}
