import { Notice } from "../types/notice";
import { ProposalAnalysisPayload } from "../types/analyzer";

const ANALYSIS_API_BASE_URL = import.meta.env.VITE_ANALYSIS_API_BASE_URL ?? "";

function isProposalAnalysisPayload(value: unknown): value is ProposalAnalysisPayload {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Partial<ProposalAnalysisPayload>;
  return Boolean(payload.noticeInfo && payload.checklist && payload.scoring);
}

export async function loadAnalyzerData(notice: Notice): Promise<ProposalAnalysisPayload> {
  const bidNo = notice.bidNtceNo || notice.number.split("-")[0];
  const bidOrd = notice.bidNtceOrd || notice.number.split("-")[1] || "000";
  let apiError = "";

  try {
    const response = await fetch(`${ANALYSIS_API_BASE_URL}/api/notices/${bidNo}/${bidOrd}/proposal-analysis`, {
      cache: "no-store",
    });
    if (response.ok) {
      const payload = await response.json();
      if (isProposalAnalysisPayload(payload)) {
        return payload;
      }
      apiError = "proposalSheets_empty";
    } else {
      apiError = `HTTP ${response.status}`;
    }
  } catch (error) {
    apiError = error instanceof Error ? error.message : "analysis_api_unreachable";
    // Fall back to the static analysis artifact below.
  }

  const response = await fetch(`data/analyses/${notice.number}.json`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(apiError || `HTTP ${response.status}`);
  }
  const analysis = (await response.json()) as { proposalSheets?: ProposalAnalysisPayload };
  if (!isProposalAnalysisPayload(analysis.proposalSheets)) {
    throw new Error(apiError || "proposalSheets_not_found");
  }
  return analysis.proposalSheets;
}
