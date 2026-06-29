import { useEffect, useMemo, useState } from "react";

import { loadProposalMappingData } from "../../api/proposalMappingApi";
import { Notice } from "../../types/notice";
import {
  ProposalMappingPayload,
  ProposalTocGroup,
  RequirementMapping,
  ScoringPagePlan,
} from "../../types/proposalMapping";
import { formatDateTime } from "../../utils/format";

type StrategyPageProps = {
  selectedNotice: Notice | null;
};

export default function StrategyPage({ selectedNotice }: StrategyPageProps) {
  const [payload, setPayload] = useState<ProposalMappingPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

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

        <TraceabilitySection mappings={payload.requirementTraceability} />
        <PagePlanSection plans={payload.scoringPagePlan} />
        <TocSection groups={payload.tableOfContents} />
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
            <col className="mappingSectionCol" />
            <col className="mappingStatusCol" />
          </colgroup>
          <thead>
            <tr>
              <th>요구사항 코드</th>
              <th>구분</th>
              <th>요구사항명(원문)</th>
              <th>세부 요구내용</th>
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
                <td>
                  {mapping.detail}
                  {mapping.source ? <small className="mappingSource">출처: {mapping.source}</small> : null}
                </td>
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

function PagePlanSection({ plans }: { plans: ScoringPagePlan[] }) {
  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Score & Page Plan</span>
          <h3>배점표 연동 페이지 배분</h3>
          <p>배점이 큰 항목일수록 더 많은 페이지를 배정하고, 대응 요구사항 코드를 함께 표시합니다.</p>
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
            <small>{plan.score ? `${plan.score}점` : "배점 확인 필요"}</small>
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
