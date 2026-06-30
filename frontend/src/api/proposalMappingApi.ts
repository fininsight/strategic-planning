import { Notice } from "../types/notice";
import { ProposalAnalysisPayload } from "../types/analyzer";
import {
  ProposalMappingPayload,
  RequirementMapping,
  ScoringPagePlan,
} from "../types/proposalMapping";

const ANALYSIS_API_BASE_URL = "http://127.0.0.1:8787";

function isProposalMappingPayload(value: unknown): value is ProposalMappingPayload {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Partial<ProposalMappingPayload>;
  return Boolean(payload.requirementTraceability && payload.scoringPagePlan && payload.tableOfContents);
}

export async function loadProposalMappingData(notice: Notice): Promise<ProposalMappingPayload> {
  const bidNo = notice.bidNtceNo || notice.number.split("-")[0];
  const bidOrd = notice.bidNtceOrd || notice.number.split("-")[1] || "000";
  let apiError = "";

  try {
    const response = await fetch(`${ANALYSIS_API_BASE_URL}/api/notices/${bidNo}/${bidOrd}/proposal-mapping`, {
      cache: "no-store",
    });
    if (response.ok) {
      const payload = await response.json();
      if (isProposalMappingPayload(payload)) {
        return payload;
      }
      apiError = "proposalMapping_empty";
    } else {
      apiError = `HTTP ${response.status}`;
    }
  } catch (error) {
    apiError = error instanceof Error ? error.message : "analysis_api_unreachable";
  }

  const response = await fetch(`data/analyses/${notice.number}.json`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(apiError || `HTTP ${response.status}`);
  }
  const analysis = (await response.json()) as {
    proposalMapping?: ProposalMappingPayload;
    proposalSheets?: ProposalAnalysisPayload;
  };
  if (!isProposalMappingPayload(analysis.proposalMapping)) {
    if (analysis.proposalSheets) {
      return buildProposalMappingFromSheets(notice, analysis.proposalSheets);
    }
    throw new Error(apiError || "proposalMapping_not_found");
  }
  return analysis.proposalMapping;
}

function buildProposalMappingFromSheets(notice: Notice, sheets: ProposalAnalysisPayload): ProposalMappingPayload {
  const requirements: RequirementMapping[] = (sheets.noticeInfo.requirements.length
    ? sheets.noticeInfo.requirements
    : [{ requirement: "제안요구사항 원문 확인", detail: "RFP 원문 요구사항 추출 결과 확인 필요", type: "확인" }]
  ).map((item, index) => {
    const text = `${item.requirement} ${item.detail}`;
    const proposalType = /정량|실적|신용|재무|경영상태|자격|증명|인증/.test(text) ? "quantitative" : "qualitative";
    const code = "code" in item && typeof item.code === "string" && item.code ? item.code : `코드 미확인-${String(index + 1).padStart(3, "0")}`;
    return {
      code,
      name: item.requirement || "요구사항",
      detail: item.detail || "원문 확인 필요",
      source: "static proposalSheets",
      proposalType,
      targetSection: proposalType === "quantitative" ? "정량제안서 Ⅱ. 입찰 참가자격 및 증빙" : "정성제안서 Ⅲ. 요구사항별 이행 방안",
      status: "mapped",
      note: "",
    };
  });
  const scoringPagePlan = buildPagePlanFromSheets(sheets, requirements);
  return {
    id: notice.number,
    generatedAt: sheets.generatedAt,
    sourceAnalysisAt: sheets.generatedAt,
    projectName: sheets.noticeInfo.summary.projectName || notice.title,
    sourceFile: sheets.sourceFile,
    requirementSourceFiles: ["static proposalSheets"],
    extractionWarnings: ["정적 분석 JSON에 저장된 proposalSheets를 보조 자료로 사용했습니다. 원문 코드가 없으면 코드 미확인으로 표시합니다."],
    documentTypes: [
      { type: "quantitative", label: "정량제안서", detected: sheets.checklist.items.some((item) => item.document.includes("정량")) },
      { type: "qualitative", label: "정성제안서", detected: sheets.checklist.items.some((item) => item.document.includes("정성") || item.document.includes("기술제안")) },
    ],
    requirementTraceability: requirements,
    scoringPagePlan,
    scoringSource: sheets.scoring.items.length ? "proposalSheets.scoring" : "정적 분석 JSON 기반 추정",
    tableOfContents: buildTocFromMappings(requirements, scoringPagePlan),
    validation: {
      totalRequirements: requirements.length,
      mappedRequirements: requirements.length,
      unmappedRequirements: [],
      ambiguousRequirements: [],
      isComplete: requirements.every((item) => !item.code.startsWith("코드 미확인")),
      message: requirements.some((item) => item.code.startsWith("코드 미확인"))
        ? "원문 요구사항 코드가 없는 항목이 있어 제안요청서 원문 재확인이 필요합니다."
        : "모든 요구사항이 원문 코드 기준으로 목차에 매핑되었습니다.",
    },
  };
}

function buildPagePlanFromSheets(sheets: ProposalAnalysisPayload, requirements: RequirementMapping[]): ScoringPagePlan[] {
  const scores = sheets.scoring.items.filter((item) => item.score > 0);
  if (!scores.length) {
    return [
      {
        scoreItem: "배점표 확인 필요",
        score: 0,
        targetSection: "정성제안서 Ⅲ. 요구사항별 이행 방안",
        proposalType: "qualitative",
        recommendedPages: 8,
        mappedRequirementCodes: requirements.map((item) => item.code),
        source: "정적 분석 JSON 기반 추정",
        detail: "",
      },
    ];
  }
  const totalScore = scores.reduce((total, item) => total + item.score, 0) || 1;
  return scores.map((item) => {
    const targetSection = /정량|경영상태|실적|인력/.test(`${item.major} ${item.middle} ${item.minor}`)
      ? "정량제안서 Ⅲ. 수행실적 및 유사사업 경험"
      : "정성제안서 Ⅲ. 요구사항별 이행 방안";
    return {
      scoreItem: item.minor || item.middle || item.major,
      score: item.score,
      targetSection,
      proposalType: targetSection.startsWith("정량") ? "quantitative" : "qualitative",
      recommendedPages: Math.max(1, Math.round((50 * item.score) / totalScore)),
      mappedRequirementCodes: requirements
        .filter((requirement) => requirement.proposalType === (targetSection.startsWith("정량") ? "quantitative" : "qualitative"))
        .map((requirement) => requirement.code),
      source: "proposalSheets.scoring",
      detail: item.detail,
    };
  });
}

function buildTocFromMappings(requirements: RequirementMapping[], plans: ScoringPagePlan[]) {
  const pages = new Map(plans.map((item) => [item.targetSection, item.recommendedPages]));
  const codes = (section: string) =>
    requirements.filter((item) => item.targetSection === section).map((item) => item.code);
  return [
    {
      proposalType: "quantitative",
      title: "정량제안서",
      children: [
        "정량제안서 Ⅰ. 제안사 일반현황",
        "정량제안서 Ⅱ. 입찰 참가자격 및 증빙",
        "정량제안서 Ⅲ. 수행실적 및 유사사업 경험",
        "정량제안서 Ⅳ. 투입인력 및 인증·가점 증빙",
      ].map((section) => ({
        title: section.replace("정량제안서 ", ""),
        section,
        requirementCodes: codes(section),
        recommendedPages: pages.get(section) ?? 1,
      })),
    },
    {
      proposalType: "qualitative",
      title: "정성제안서",
      children: [
        "정성제안서 Ⅰ. 사업 이해 및 추진 방향",
        "정성제안서 Ⅱ. 제안 전략 및 차별화 방향",
        "정성제안서 Ⅲ. 요구사항별 이행 방안",
        "정성제안서 Ⅳ. 운영 및 확산 계획",
        "정성제안서 Ⅴ. 수행조직 및 투입인력",
        "정성제안서 Ⅵ. 품질·보안·위험관리",
      ].map((section) => ({
        title: section.replace("정성제안서 ", ""),
        section,
        requirementCodes: codes(section),
        recommendedPages: pages.get(section) ?? 3,
      })),
    },
  ];
}
