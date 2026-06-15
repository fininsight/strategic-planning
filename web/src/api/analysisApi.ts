import { NoticeAnalysis } from "../types/analysis";

const ANALYSIS_API_BASE_URL = "http://127.0.0.1:8787";

export async function loadNoticeAnalysis(bidNo: string, bidOrd: string): Promise<NoticeAnalysis> {
  const response = await fetch(`${ANALYSIS_API_BASE_URL}/api/notices/${bidNo}/${bidOrd}/analysis`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.message || "분석 API 호출에 실패했습니다.");
  }
  return payload as NoticeAnalysis;
}
