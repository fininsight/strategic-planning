import { useCallback, useEffect, useMemo, useState } from "react";

import { loadProposalMappingData, loadStrategyMarketResearchData } from "../../api/proposalMappingApi";
import { Notice } from "../../types/notice";
import {
  ProposalMappingPayload,
  ProposalTocGroup,
  RequirementMapping,
  ScoringPagePlan,
  StrategyAdvantage,
  StrategyFactCheck,
  StrategyResearchPayload,
  StrategySource,
} from "../../types/proposalMapping";
import { formatDateTime } from "../../utils/format";

type StrategyPageProps = {
  selectedNotice: Notice | null;
};

type StrategyView = "mapping" | "research";

const strategyViews: { id: StrategyView; label: string; caption: string }[] = [
  { id: "mapping", label: "요구사항 추출", caption: "원문 요구사항과 제안서 목차 매핑" },
  { id: "research", label: "시장·경쟁 리서치", caption: "웹검색 AI 기반 경쟁·팩트체크" },
];

export default function StrategyPage({ selectedNotice }: StrategyPageProps) {
  const [payload, setPayload] = useState<ProposalMappingPayload | null>(null);
  const [activeView, setActiveView] = useState<StrategyView>("mapping");
  const [researchPayload, setResearchPayload] = useState<StrategyResearchPayload | null>(null);
  const [isResearchLoading, setIsResearchLoading] = useState(false);
  const [researchError, setResearchError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const refreshResearch = useCallback(
    async (force = false) => {
      if (!selectedNotice) {
        return;
      }

      setIsResearchLoading(true);
      setResearchError("");

      try {
        const data = await loadStrategyMarketResearchData(selectedNotice, force);
        setResearchPayload(data);
      } catch (loadError) {
        setResearchPayload(null);
        setResearchError(loadError instanceof Error ? loadError.message : "시장·경쟁 리서치를 불러오지 못했습니다.");
      } finally {
        setIsResearchLoading(false);
      }
    },
    [selectedNotice],
  );

  useEffect(() => {
    let ignore = false;

    async function load() {
      setIsLoading(true);
      setError("");

      if (!selectedNotice) {
        setPayload(null);
        setError("대시보드에서 공고를 선택하면 전략 수립 결과가 표시됩니다.");
        setIsLoading(false);
        return;
      }

      try {
        const data = await loadProposalMappingData(selectedNotice);
        if (!ignore) {
          setPayload(data);
        }
      } catch (loadError) {
        if (!ignore) {
          setPayload(null);
          setError(loadError instanceof Error ? loadError.message : "전략 수립 데이터를 불러오지 못했습니다.");
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    load();

    return () => {
      ignore = true;
    };
  }, [selectedNotice]);

  useEffect(() => {
    let ignore = false;

    async function loadResearch() {
      if (activeView !== "research" || !selectedNotice || researchPayload) {
        return;
      }

      if (!ignore) {
        await refreshResearch(false);
      }
    }

    loadResearch();

    return () => {
      ignore = true;
    };
  }, [activeView, selectedNotice, researchPayload, refreshResearch]);

  useEffect(() => {
    setResearchPayload(null);
    setResearchError("");
  }, [selectedNotice]);

  const pageTotal = useMemo(
    () => payload?.scoringPagePlan.reduce((total, item) => total + item.recommendedPages, 0) ?? 0,
    [payload],
  );

  if (isLoading) {
    return <StrategyState message="요구사항-제안서 목차 매핑을 생성하는 중입니다." />;
  }

  if (error || !payload) {
    return <StrategyState message={error || "전략 수립 결과가 없습니다."} selectedNotice={selectedNotice} />;
  }

  return (
    <>
      <header className="topbar analysisTopbar">
        <div className="titleRow">
          <span className="strategyMark" aria-hidden="true" />
          <div>
            <h2>전략 수립</h2>
            <p>{payload.sourceFile || selectedNotice?.title}</p>
          </div>
        </div>
        <p className="lastUpdated">마지막 업데이트: {formatDateTime(payload.generatedAt)}</p>
      </header>

      <section className="content proposalAnalysisContent strategyContent">
        <section className="proposalHero strategyHero">
          <div>
            <span>STEP 5 · 요구사항-제안서 목차 맵핑</span>
            <h3>{payload.projectName || selectedNotice?.title || "제안 전략 수립"}</h3>
            <p>제안요청서의 요구사항 원문 코드를 기준으로 정량/정성 제안서 목차를 확정합니다.</p>
          </div>
          <dl>
            <div>
              <dt>요구사항</dt>
              <dd>{payload.validation.totalRequirements}</dd>
            </div>
            <div>
              <dt>매핑 완료</dt>
              <dd>{payload.validation.mappedRequirements}</dd>
            </div>
            <div>
              <dt>누락</dt>
              <dd>{payload.validation.unmappedRequirements.length}</dd>
            </div>
            <div>
              <dt>권장 페이지</dt>
              <dd>{pageTotal}</dd>
            </div>
          </dl>
        </section>

        <section className={payload.validation.isComplete ? "strategyValidation complete" : "strategyValidation warning"}>
          <div>
            <strong>{payload.validation.isComplete ? "누락 0 검증 완료" : "추가 확인 필요"}</strong>
            <p>{payload.validation.message}</p>
            {payload.requirementSourceFiles?.length ? (
              <small>요구사항 기준 문서: {payload.requirementSourceFiles.join(", ")}</small>
            ) : null}
          </div>
          <div className="documentTypePills">
            {payload.documentTypes.map((item) => (
              <span className={item.detected ? "detected" : ""} key={item.type}>
                {item.label} {item.detected ? "인식" : "확인"}
              </span>
            ))}
          </div>
        </section>

        <section className="proposalTabs strategySubTabs" aria-label="전략 수립 세부 단계">
          {strategyViews.map((view) => (
            <button
              className={view.id === activeView ? "activeProposalTab" : ""}
              type="button"
              onClick={() => setActiveView(view.id)}
              key={view.id}
            >
              <strong>{view.label}</strong>
              <span>{view.caption}</span>
            </button>
          ))}
        </section>

        {activeView === "mapping" ? (
          <>
            <TraceabilitySection mappings={payload.requirementTraceability} />
            <PagePlanSection plans={payload.scoringPagePlan} scoringSource={payload.scoringSource} />
            <TocSection groups={payload.tableOfContents} />
          </>
        ) : (
          <MarketResearchSection
            payload={researchPayload}
            isLoading={isResearchLoading}
            error={researchError}
            onRefresh={() => refreshResearch(true)}
          />
        )}
      </section>
    </>
  );
}

function StrategyState({
  message,
  selectedNotice = null,
}: {
  message: string;
  selectedNotice?: Notice | null;
}) {
  return (
    <>
      <header className="topbar">
        <div className="titleRow">
          <h2>전략 수립</h2>
        </div>
      </header>
      <section className="content">
        <div className="analyzerEmptyState">
          <strong>{message}</strong>
          {selectedNotice ? <p>{selectedNotice.number} · {selectedNotice.title}</p> : null}
        </div>
      </section>
    </>
  );
}

function TraceabilitySection({ mappings }: { mappings: RequirementMapping[] }) {
  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Traceability Matrix</span>
          <h3>요구사항-목차 매핑</h3>
          <p>제안요청서의 요구사항 코드와 명칭을 임의 변경 없이 유지하고, 대응 목차를 1:1로 연결합니다.</p>
        </div>
        <b>{mappings.length}개</b>
      </div>

      <div className="proposalTableWrap">
        <table className="proposalTable strategyMappingTable">
          <colgroup>
            <col className="mappingCodeCol" />
            <col className="mappingTypeCol" />
            <col className="mappingNameCol" />
            <col className="mappingDetailCol" />
            <col className="mappingSourceCol" />
            <col className="mappingSectionCol" />
            <col className="mappingStatusCol" />
          </colgroup>
          <thead>
            <tr>
              <th>요구사항 코드</th>
              <th>구분</th>
              <th>요구사항명(원문)</th>
              <th>세부 요구내용</th>
              <th>출처</th>
              <th>대응 목차</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            {mappings.map((mapping) => (
              <tr className={mapping.status === "mapped" ? "" : "warningMappingRow"} key={mapping.code}>
                <td>
                  <strong>{mapping.code}</strong>
                </td>
                <td>{mapping.proposalType === "quantitative" ? "정량" : "정성"}</td>
                <td>{mapping.name}</td>
                <td>{mapping.detail}</td>
                <td className="mappingSourceCell">{mapping.source || "원문 확인 필요"}</td>
                <td>{mapping.targetSection}</td>
                <td>
                  <span className={mapping.status === "mapped" ? "mappingStatus mapped" : "mappingStatus warning"}>
                    {mapping.status === "mapped" ? "매핑 완료" : "확인 필요"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PagePlanSection({ plans, scoringSource = "" }: { plans: ScoringPagePlan[]; scoringSource?: string }) {
  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Score & Page Plan</span>
          <h3>배점표 연동 페이지 배분</h3>
          <p>제안서 기술능력평가 평가항목 및 배점 한도를 기준으로 페이지를 배정합니다.</p>
          {scoringSource ? <small className="mappingSource">배점 기준: {scoringSource}</small> : null}
        </div>
        <b>{plans.reduce((total, item) => total + item.recommendedPages, 0)}p</b>
      </div>

      <div className="pagePlanGrid">
        {plans.map((plan) => (
          <article key={`${plan.scoreItem}-${plan.targetSection}`}>
            <div>
              <span>{plan.proposalType === "quantitative" ? "정량" : "정성"}</span>
              <strong>{plan.scoreItem}</strong>
              <p>{plan.targetSection}</p>
            </div>
            <b>{plan.recommendedPages}p</b>
            <small>{plan.score ? `${plan.score}점 · ${plan.source || "배점표"}` : "배점 확인 필요"}</small>
            {plan.detail ? <p className="pagePlanDetail">{plan.detail}</p> : null}
            <div className="mappingCodeList">
              {plan.mappedRequirementCodes.length ? plan.mappedRequirementCodes.map((code) => <em key={code}>{code}</em>) : <em>요구사항 연결 확인</em>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function TocSection({ groups }: { groups: ProposalTocGroup[] }) {
  return (
    <section className="proposalSheetGrid strategyTocGrid">
      {groups.map((group) => (
        <article className="proposalPanel" key={group.proposalType}>
          <div className="proposalPanelHeader">
            <div>
              <span>{group.proposalType === "quantitative" ? "Quantitative Proposal" : "Qualitative Proposal"}</span>
              <h3>{group.title}</h3>
            </div>
            <b>{group.children.reduce((total, item) => total + item.recommendedPages, 0)}p</b>
          </div>
          <ol className="tocList">
            {group.children.map((section) => (
              <li key={section.section}>
                <div>
                  <strong>{section.title}</strong>
                  <p>{section.requirementCodes.length ? section.requirementCodes.join(", ") : "요구사항 직접 매핑 없음"}</p>
                </div>
                <span>{section.recommendedPages}p</span>
              </li>
            ))}
          </ol>
        </article>
      ))}
    </section>
  );
}

function MarketResearchSection({
  payload,
  isLoading,
  error,
  onRefresh,
}: {
  payload: StrategyResearchPayload | null;
  isLoading: boolean;
  error: string;
  onRefresh: () => void;
}) {
  if (isLoading) {
    return <StrategyInlineState message="웹검색 AI로 시장·경쟁 리서치를 생성하는 중입니다." />;
  }

  if (error || !payload) {
    return <StrategyInlineState message={error || "시장·경쟁 리서치 결과가 없습니다."} />;
  }

  const verifiedClaims = payload.factChecks.filter((item) => item.status === "verified").length;
  const unverifiedClaims = payload.factChecks.length - verifiedClaims;

  return (
    <>
      <section className={payload.status === "verified" ? "strategyValidation complete" : "strategyValidation warning"}>
        <div>
          <strong>{payload.status === "verified" ? "출처 검증 완료" : "출처 검증 필요"}</strong>
          <p>{payload.executiveSummary}</p>
          <small>원칙: 출처 없는 수치·시장점유율·수주사실은 제안서에 사용하지 않습니다.</small>
        </div>
        <div className="researchMetricPills">
          <span>{payload.competitors.length}개 경쟁 후보</span>
          <span>{payload.marketStats.length}개 시장 수치</span>
          <span>{unverifiedClaims}개 미검증</span>
          <button type="button" onClick={onRefresh}>
            재조사
          </button>
        </div>
      </section>

      <section className="researchGrid">
        <ResearchListPanel
          eyebrow="Competitive Researcher"
          title="경쟁사·예상 컨소시엄"
          count={payload.competitors.length}
          items={payload.competitors.map((item) => ({
            title: safeText(item.name, "경쟁 후보 확인 필요"),
            body: joinText([item.expectedRole, item.rationale], "경쟁 후보의 역할과 근거 확인 필요"),
            meta: safeArray(item.likelyPartners).join(", ") || "파트너 구성 확인 필요",
            sources: safeSources(item.sources),
            emptySourceLabel: "AI 전략 초안",
          }))}
        />
        <ResearchListPanel
          eyebrow="Precedents"
          title="유사 선행사례"
          count={payload.precedents.length}
          empty="웹검색 AI가 확인한 수주사실이 아직 없습니다."
          items={payload.precedents.map((item) => ({
            title: safeText(item.projectName, "유사 선행사례 확인 필요"),
            body: joinText([item.buyer, item.winner, item.year], "발주기관·수주사·연도 확인 필요"),
            meta: safeText(item.contractAmount || item.relevance, "계약금액 또는 관련성 확인 필요"),
            sources: safeSources(item.sources),
          }))}
        />
      </section>

      <section className="researchGrid">
        <ResearchListPanel
          eyebrow="Market Size"
          title="시장 규모·성장률"
          count={payload.marketStats.length}
          items={payload.marketStats.map((item) => ({
            title: `${safeText(item.metric, "시장 지표")}: ${safeText(item.value, "수치 확인 필요")}`,
            body: joinText([item.period, item.interpretation], "기간과 해석 확인 필요"),
            meta: item.verification === "verified" ? "검증 완료" : "검증 전 사용 금지",
            sources: safeSources(item.sources),
            warning: item.verification !== "verified",
          }))}
        />
        <ResearchListPanel
          eyebrow="Tech & Policy"
          title="기술 트렌드·정책 흐름"
          count={payload.trends.length}
          items={payload.trends.map((item) => ({
            title: safeText(item.title, "기술 트렌드 확인 필요"),
            body: safeText(item.detail, "상세 동향 확인 필요"),
            meta: safeText(item.implication, "제안 반영 포인트 확인 필요"),
            sources: safeSources(item.sources),
            emptySourceLabel: "AI 전략 초안",
          }))}
        />
      </section>

      <section className="proposalPanel fullProposalPanel">
        <div className="proposalPanelHeader">
          <div>
            <span>FinInsight Positioning</span>
            <h3>핀인사이트 경쟁우위와 보완점</h3>
            <p>Krayon·InsightStudio·InsightPage를 평가항목에 연결하되, 인증·실적은 회사자료 RAG 근거로 확정합니다.</p>
          </div>
          <b>{payload.advantages.length}개</b>
        </div>
        <div className="advantageGrid">
          {payload.advantages.map((item) => (
            <AdvantageCard item={item} key={`${item.evaluationItem}-${item.priority}`} />
          ))}
        </div>
      </section>

      <section className="proposalPanel fullProposalPanel">
        <div className="proposalPanelHeader">
          <div>
            <span>Company RAG</span>
            <h3>핀인사이트 내부 근거</h3>
            <p>회사소개서·수행실적·솔루션 자료에서 검색된 근거입니다. 외부 수치와 수주사실은 별도 웹 출처가 필요합니다.</p>
          </div>
          <b>{payload.companyEvidence?.length ?? 0}개</b>
        </div>
        <div className="researchList companyEvidenceList">
          {payload.companyEvidence?.length ? (
            payload.companyEvidence.slice(0, 6).map((item) => (
              <article key={item.chunkId}>
                <strong>{safeText(item.fileName, "회사자료")}</strong>
                <p>{safeText(item.text, "검색된 근거 텍스트가 없습니다.")}</p>
                <small>
                  {safeText(item.docType, "회사자료")} · match {item.score.toFixed(2)}
                </small>
              </article>
            ))
          ) : (
            <div className="researchEmpty">회사자료 RAG 검색 결과가 없습니다.</div>
          )}
        </div>
      </section>

      <section className="proposalPanel fullProposalPanel">
        <div className="proposalPanelHeader">
          <div>
            <span>Proposal Fact Checker</span>
            <h3>팩트체크 로그</h3>
            <p>검증 통과 항목과 미검증 항목을 분리해 제안서 사용 가능 여부를 관리합니다.</p>
          </div>
          <b>{verifiedClaims}/{payload.factChecks.length}</b>
        </div>
        <div className="factCheckList">
          {payload.factChecks.map((item) => (
            <FactCheckRow item={item} key={item.claim} />
          ))}
        </div>
      </section>

      <section className="swotGrid">
        {(["S", "W", "O", "T"] as const).map((type) => (
          <article className="proposalPanel" key={type}>
            <div className="swotHeader">{type}</div>
            {payload.swot
              .filter((item) => item.type === type)
              .map((item) => (
                <div className="swotItem" key={`${type}-${item.title}`}>
                  <strong>{safeText(item.title, "SWOT 항목 확인 필요")}</strong>
                  <p>{safeText(item.detail, "상세 내용 확인 필요")}</p>
                </div>
              ))}
          </article>
        ))}
      </section>

      {payload.warnings.length ? (
        <section className="researchWarnings">
          {payload.warnings.map((warning) => (
            <span key={warning}>{warning}</span>
          ))}
        </section>
      ) : null}
    </>
  );
}

function ResearchListPanel({
  eyebrow,
  title,
  count,
  items,
  empty = "확인된 항목이 없습니다.",
}: {
  eyebrow: string;
  title: string;
  count: number;
  items: { title: string; body: string; meta: string; sources: StrategySource[]; warning?: boolean; emptySourceLabel?: string }[];
  empty?: string;
}) {
  return (
    <section className="proposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>{eyebrow}</span>
          <h3>{title}</h3>
        </div>
        <b>{count}개</b>
      </div>
      <div className="researchList">
        {items.length ? (
          items.map((item) => (
            <article className={item.warning ? "needsVerification" : ""} key={`${item.title}-${item.meta}`}>
              <strong>{item.title}</strong>
              <p>{item.body}</p>
              <small>{item.meta}</small>
              <SourceLinks sources={item.sources} emptyLabel={item.emptySourceLabel} />
            </article>
          ))
        ) : (
          <div className="researchEmpty">{empty}</div>
        )}
      </div>
    </section>
  );
}

function AdvantageCard({ item }: { item: StrategyAdvantage }) {
  return (
    <article>
      <span>{item.priority === "high" ? "우선 반영" : "보완 검토"}</span>
      <strong>{safeText(item.evaluationItem, "평가항목 확인 필요")}</strong>
      <p>{safeText(item.finInsightEdge, "핀인사이트 우위 근거 확인 필요")}</p>
      <small>필요 증빙: {safeText(item.evidenceNeeded, "사내 증빙 확인 필요")}</small>
      <em>{safeText(item.competitorComparison, "경쟁사 비교 근거 확인 필요")}</em>
    </article>
  );
}

function FactCheckRow({ item }: { item: StrategyFactCheck }) {
  return (
    <article className={item.status === "verified" ? "verified" : "blocked"}>
      <div>
        <strong>{safeText(item.claim, "팩트체크 항목 확인 필요")}</strong>
        <p>{safeText(item.note, "검증 메모 확인 필요")}</p>
        <SourceLinks sources={safeSources(item.sources)} />
      </div>
      <span>{item.status === "verified" ? "사용 가능" : "사용 금지"}</span>
    </article>
  );
}

function SourceLinks({ sources, emptyLabel = "출처 링크 없음" }: { sources: StrategySource[]; emptyLabel?: string }) {
  if (!sources.length) {
    return <div className="sourceLinks emptySource">{emptyLabel}</div>;
  }
  return (
    <div className="sourceLinks">
      {sources.slice(0, 3).map((source) => (
        <a href={source.url} target="_blank" rel="noreferrer" key={`${source.title}-${source.url}`}>
          {source.title || source.publisher || "출처"}
        </a>
      ))}
    </div>
  );
}

function safeText(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function joinText(values: unknown[], fallback: string) {
  const parts = values.filter((value): value is string => typeof value === "string" && Boolean(value.trim()));
  return parts.length ? parts.join(" · ") : fallback;
}

function safeArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : [];
}

function safeSources(value: unknown): StrategySource[] {
  return Array.isArray(value)
    ? value.filter((source): source is StrategySource => Boolean(source && typeof source === "object" && "url" in source))
    : [];
}

function StrategyInlineState({ message }: { message: string }) {
  return (
    <section className="analyzerEmptyState">
      <strong>{message}</strong>
      <p>웹검색 AI 결과가 없으면 검증 대기 체크리스트만 표시됩니다.</p>
    </section>
  );
}
