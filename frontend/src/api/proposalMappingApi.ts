import { Notice } from "../types/notice";
import { ProposalAnalysisPayload } from "../types/analyzer";
import {
  ProposalMappingPayload,
  RequirementMapping,
  ScoringPagePlan,
  StrategyResearchPayload,
} from "../types/proposalMapping";
import { apiUrl, fetchJson } from "./baseUrl";

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
    const payload = await fetchJson<unknown>(apiUrl(`/api/notices/${bidNo}/${bidOrd}/proposal-mapping`), {
      cache: "no-store",
    });
    if (isProposalMappingPayload(payload)) {
      return payload;
    }
    apiError = "proposalMapping_empty";
  } catch (error) {
    apiError = error instanceof Error ? error.message : "analysis_api_unreachable";
  }

  try {
    const analysis = await fetchJson<{
      proposalMapping?: ProposalMappingPayload;
      proposalSheets?: ProposalAnalysisPayload;
    }>(`data/analyses/${notice.number}.json`, { cache: "no-store" });
    if (isProposalMappingPayload(analysis.proposalMapping)) {
      return analysis.proposalMapping;
    }
    if (analysis.proposalSheets) {
      return buildProposalMappingFromSheets(notice, analysis.proposalSheets);
    }
  } catch {
    // Prefer the API error below; missing static artifacts are only a fallback detail.
  }
  throw new Error(apiError || "proposalMapping_not_found");
}

function isStrategyResearchPayload(value: unknown): value is StrategyResearchPayload {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Partial<StrategyResearchPayload>;
  return Boolean(payload.factChecks && payload.marketStats && payload.competitors && payload.advantages);
}

export async function loadStrategyMarketResearchData(notice: Notice, refresh = false): Promise<StrategyResearchPayload> {
  const bidNo = notice.bidNtceNo || notice.number.split("-")[0];
  const bidOrd = notice.bidNtceOrd || notice.number.split("-")[1] || "000";
  let apiError = "";

  try {
    const payload = await fetchJsonWithTimeout<unknown>(
      apiUrl(`/api/notices/${bidNo}/${bidOrd}/market-research${refresh ? "?refresh=1" : ""}`),
      { cache: "no-store" },
      90000,
    );
    if (isStrategyResearchPayload(payload)) {
      return payload;
    }
    apiError = "marketResearch_empty";
  } catch (error) {
    apiError = error instanceof Error ? error.message : "analysis_api_unreachable";
  }

  try {
    const analysis = await fetchJson<{ marketResearch?: StrategyResearchPayload }>(`data/analyses/${notice.number}.json`, {
      cache: "no-store",
    });
    if (isStrategyResearchPayload(analysis.marketResearch)) {
      return analysis.marketResearch;
    }
  } catch {
    // Use generated fallback below.
  }
  return buildMarketResearchFallback(notice, apiError);
}

async function fetchJsonWithTimeout<T>(url: string, init: RequestInit, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchJson<T>(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("시장·경쟁 리서치 생성 시간이 길어져 중단했습니다. 잠시 후 재조사하거나 서버 로그를 확인해주세요.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
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

function buildMarketResearchFallback(notice: Notice, apiError: string): StrategyResearchPayload {
  const projectName = notice.title || "선택 공고";
  return {
    id: notice.number,
    generatedAt: new Date().toISOString(),
    projectName,
    sourceMode: "fallback",
    status: "needs_verification",
    executiveSummary:
      "웹검색 AI 리서치 결과가 아직 생성되지 않았습니다. 아래 항목은 제안서 작성 전 검증해야 할 리서치 체크리스트이며, 수치와 수주사실은 출처가 확인되기 전까지 사용 금지입니다.",
    competitors: [
      {
        name: "동종 공공 SI·데이터 분석 전문사",
        expectedRole: "주관 또는 데이터/AI 분석 부문 참여 후보",
        rationale: `${projectName}의 과업 범위와 유사한 공공 데이터·AI·시스템 구축 실적 보유사가 경쟁 후보가 될 수 있습니다.`,
        likelyPartners: ["공공 SI", "클라우드/인프라", "데이터 컨설팅"],
        sources: [],
      },
    ],
    precedents: [],
    marketStats: [
      {
        metric: "시장 규모·성장률",
        value: "출처 확인 전",
        period: "2023~2025 자료 우선",
        interpretation: "공식 통계, 조달 수주 이력, 신뢰 가능한 리서치 기관 자료를 교차 확인해야 합니다.",
        verification: "unverified",
        sources: [],
      },
    ],
    trends: [
      {
        title: "웹검색 AI 리서치 필요",
        detail: "정책·제도 흐름, 유사 발주 동향, 데이터/AI 기술 트렌드를 검색 기반으로 확인해야 합니다.",
        implication: "출처 링크가 붙은 항목만 제안서 본문에 반영합니다.",
        sources: [],
      },
    ],
    swot: [
      {
        type: "S",
        title: "솔루션 기반 제안 구조",
        detail: "Krayon·InsightStudio·InsightPage를 요구사항 대응 기능과 산출물 생성 흐름으로 연결할 수 있으나, 실제 인증·실적 수치는 사내 증빙 확인이 필요합니다.",
      },
      {
        type: "W",
        title: "사내 실적·인증 근거 미연동",
        detail: "현재 화면은 웹검색 AI 중심입니다. 회사 소개서, 인증서, 수행실적 자료에서 확인되지 않은 내부 강점 수치는 확정하지 않습니다.",
      },
    ],
    advantages: [
      {
        evaluationItem: "기술 이해도 및 구현 방안",
        finInsightEdge: "Krayon·InsightStudio·InsightPage를 요구사항별 산출물과 연결해 제안할 수 있습니다.",
        evidenceNeeded: "각 솔루션 기능 명세, 구축 사례, 인증·보안 자료",
        competitorComparison: "경쟁사 대비 우위 판단은 유사 실적과 평가항목 배점 확인 후 확정합니다.",
        priority: "high",
        evidenceSources: [],
      },
    ],
    factChecks: [
      {
        claim: "출처 없는 수치·시장점유율·수주사실은 제안서 사용 금지",
        status: "unverified",
        note: apiError ? `리서치 API 미사용: ${apiError}` : "웹검색 AI 실행 전",
        sources: [],
      },
    ],
    companyEvidence: [],
    webEvidence: [],
    researchQueries: {
      coreContext: {
        projectName,
        agency: notice.agency || "발주기관 확인 필요",
        domain: notice.industry || "공공 정보화",
      },
      competitors: [
        `"${projectName}" 수주 기업`,
        `"${notice.industry || "공공 정보화"}" 사업 주요 기업`,
        `"${notice.agency || "발주기관"}" "${notice.industry || "공공 정보화"}" 계약`,
      ],
      precedents: [
        `"${notice.agency || "발주기관"}" 유사 구축 사업`,
        `"${notice.industry || "공공 정보화"}" 나라장터 입찰 결과`,
      ],
      marketTrends: [
        `"${notice.industry || "공공 정보화"}" 시장 규모 성장률 2024 2025`,
        `"${notice.industry || "공공 정보화"}" 정책 동향 NIA NIPA ETRI`,
      ],
      companyPositioning: ['"핀인사이트" Krayon InsightStudio InsightPage', '"핀인사이트" 수행실적 인증'],
      factCheck: ["KOSIS 통계청 시장 규모", "나라장터 입찰결과 수주사 계약금액", "법제처 관련 법령 고시"],
    },
    researchMemory: {
      verifiedNumbers: [],
      verifiedWins: [],
      usableCitations: [],
      finInsightEdges: [],
      gaps: ["웹 출처와 사내 증빙 확인 전"],
    },
    researchQuality: {
      sourcedFacts: 0,
      verifiedClaims: 0,
      verifiedMarketStats: 0,
      sourcedCompetitors: 0,
      sourcedPrecedents: 0,
      sourcedTrends: 0,
    },
    researchPrompt:
      "경쟁사/컨소시엄, 유사 선행사례, 시장 규모·성장률, 기술 트렌드, SWOT, 핀인사이트 경쟁우위를 출처 링크와 함께 조사한다.",
    warnings: ["검증 전 fallback 데이터입니다.", "회사 강점은 확인 가능한 사내 증빙으로 보강해야 합니다."],
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
