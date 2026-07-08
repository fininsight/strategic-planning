import { Notice } from "../types/notice";
import { ProposalAnalysisPayload } from "../types/analyzer";
import { apiUrl, fetchJson } from "./baseUrl";

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
    const payload = await fetchJson<unknown>(apiUrl(`/api/notices/${bidNo}/${bidOrd}/proposal-analysis`), {
      cache: "no-store",
    });
    if (isProposalAnalysisPayload(payload)) {
      return payload;
    }
    apiError = "proposalSheets_empty";
  } catch (error) {
    apiError = error instanceof Error ? error.message : "analysis_api_unreachable";
    // Fall back to the static analysis artifact below.
  }

  const analysis = await fetchJson<{ proposalSheets?: ProposalAnalysisPayload }>(`data/analyses/${notice.number}.json`, {
    cache: "no-store",
  });
  if (!isProposalAnalysisPayload(analysis.proposalSheets)) {
    throw new Error(apiError || "proposalSheets_not_found");
  }
  return analysis.proposalSheets;
}
