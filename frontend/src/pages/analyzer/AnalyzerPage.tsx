import { useEffect, useMemo, useState } from "react";

import { loadAnalyzerData, loadChecklistState, saveChecklistState } from "../../api/analyzerApi";
import { Notice } from "../../types/notice";
import {
  NoticeInfoDetail,
  NoticeInfoDetailGroup,
  NoticeRequirement,
  ProposalAnalysisPayload,
  ProposalChecklistItem,
  ProposalScoreItem,
} from "../../types/analyzer";
import { formatDateTime } from "../../utils/format";

type AnalysisTab = "notice" | "requirements" | "checklist" | "scoring";

const tabs: { id: AnalysisTab; label: string; caption: string }[] = [
  { id: "notice", label: "공고정보", caption: "사업·평가·제출 조건" },
  { id: "requirements", label: "요구사항", caption: "원문 코드와 제안 요구" },
  { id: "checklist", label: "제출서류", caption: "주관기관 제출 체크리스트" },
  { id: "scoring", label: "배점표", caption: "평가항목과 공략 전략" },
];

type AnalyzerPageProps = {
  selectedNotice: Notice | null;
};

export default function AnalyzerPage({ selectedNotice }: AnalyzerPageProps) {
  const [payload, setPayload] = useState<ProposalAnalysisPayload | null>(null);
  const [activeTab, setActiveTab] = useState<AnalysisTab>("notice");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;

    async function load() {
      setIsLoading(true);
      setError("");

      if (!selectedNotice) {
        setPayload(null);
        setError("대시보드에서 공고를 선택하면 분석 결과가 표시됩니다.");
        setIsLoading(false);
        return;
      }

      try {
        const data = await loadAnalyzerData(selectedNotice);
        if (!ignore) {
          setPayload(data);
          setError("");
        }
      } catch {
        if (!ignore) {
          setPayload(null);
          setError("공고 첨부파일 분석 JSON을 읽지 못했습니다.");
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

  const checklistStats = useMemo(() => {
    const items = payload?.checklist.items ?? [];
    const done = items.filter((item) => item.organizations.some((org) => org.checked)).length;
    const go = items.filter((item) => item.owner === "GO").length;
    return { total: items.length, done, go };
  }, [payload]);

  if (isLoading) {
    return <AnalysisState message="제안 분석 결과를 불러오는 중입니다." />;
  }

  if (error || !payload) {
    return <AnalysisState message={error || "분석 결과가 없습니다."} selectedNotice={selectedNotice} />;
  }

  return (
    <>
      <header className="topbar analysisTopbar">
        <div className="titleRow">
          <span className="analysisMark" aria-hidden="true" />
          <div>
            <h2>제안 분석</h2>
            <p>{payload.sourceFile}</p>
          </div>
        </div>
        <p className="lastUpdated">마지막 업데이트: {formatDateTime(payload.generatedAt)}</p>
      </header>

      <section className="content proposalAnalysisContent">
        <section className="proposalHero">
          <div>
            <span>사업명</span>
            <h3>{payload.noticeInfo.summary.projectName || "공고 분석 결과"}</h3>
            <p>{selectedNotice
              ? `${selectedNotice.number} | ${payload.noticeInfo.summary.agency}`
              : "선택된 공고가 없습니다."}</p>
            <p></p>
          </div>
          <dl>
            <div>
              <dt>제출서류</dt>
              <dd>{checklistStats.total}건</dd>
            </div>
            <div>
              <dt>GO 발급</dt>
              <dd>{checklistStats.go}건</dd>
            </div>
            <div>
              <dt>총점</dt>
              <dd>{payload.scoring.totals.score || 100}점</dd>
            </div>
            <div>
              <dt>A등급 항목</dt>
              <dd>{payload.scoring.totals.gradeA}개</dd>
            </div>
          </dl>
        </section>


        <section className="proposalTabs" aria-label="제안 분석 시트">
          {tabs.map((tab) => (
            <button
              className={tab.id === activeTab ? "activeProposalTab" : ""}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              key={tab.id}
            >
              <strong>{tab.label}</strong>
              <span>{tab.caption}</span>
            </button>
          ))}
        </section>

        {activeTab === "notice" ? <NoticeInfoTab payload={payload} /> : null}
        {activeTab === "requirements" ? <RequirementsTab payload={payload} /> : null}
        {activeTab === "checklist" ? <ChecklistTab payload={payload} /> : null}
        {activeTab === "scoring" ? <ScoringTab payload={payload} /> : null}
      </section>
    </>
  );
}

function AnalysisState({
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
          <h2>제안 분석</h2>
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

function NoticeInfoTab({ payload }: { payload: ProposalAnalysisPayload }) {
  const detailGroups = payload.noticeInfo.detailGroups?.length
    ? payload.noticeInfo.detailGroups
    : buildFallbackDetailGroups(payload);
  const risks = payload.noticeInfo.risks ?? [];
  const clarifications = payload.noticeInfo.clarifications ?? [];

  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Sheet 1</span>
          <h3>핵심정보 요약</h3>
          <p>사업 개요, 평가 방식, 제출 형식, 일정·방법, 공동수급 의무를 상위 항목 기준으로 분리했습니다.</p>
        </div>
        <b>{payload.noticeInfo.summary.noticeNumber || "공고번호 미확인"}</b>
      </div>

      <OverviewSubTab groups={detailGroups} />
      <RiskQuestionSubTab risks={risks} clarifications={clarifications} />
    </section>
  );
}

function buildFallbackDetailGroups(payload: ProposalAnalysisPayload): NoticeInfoDetailGroup[] {
  const details = payload.noticeInfo.details;
  const summary = payload.noticeInfo.summary;
  const valueFor = (...labels: string[]) => {
    for (const label of labels) {
      const match = details.find((item) => item.label === label);
      if (match?.value) {
        return match.value;
      }
    }
    return "";
  };
  const noteFor = (...labels: string[]) => {
    for (const label of labels) {
      const match = details.find((item) => item.label === label);
      if (match?.note) {
        return match.note;
      }
    }
    return "";
  };
  const row = (label: string, value: string, note = ""): NoticeInfoDetail => ({ label, value, note });

  return [
    {
      category: "사업 개요",
      items: [
        row("사업명", summary.projectName || valueFor("사업(과제)명", "공고명")),
        row("발주처", summary.agency || valueFor("수요기관")),
        row("예산", summary.budget || valueFor("사업금액")),
        row("사업 기간", summary.period || valueFor("납품기한(사업수행기간)")),
        row("과업 범위", valueFor("비고")),
      ],
    },
    {
      category: "평가 방식",
      items: [
        row("계약/낙찰 방식", summary.contractMethod || summary.method || valueFor("계약방법", "낙찰방법", "입찰방식")),
        row("협상/적격심사 여부", inferEvaluationMethod(summary.method || valueFor("계약방법", "낙찰방법", "낙찰방법세부기준"))),
        row("기술:가격 배점비", extractTechPriceRatio(valueFor("낙찰방법세부기준"))),
        row("평가 절차", valueFor("낙찰방법세부기준", "제안 발표")),
      ],
    },
    {
      category: "제출 형식 제한",
      items: [
        row("제안서 매수 제한", ""),
        row("규격", ""),
        row("원본/사본/PDF/HWPX 등 형식", valueFor("제안 발표")),
      ],
    },
    {
      category: "일정·방법",
      items: [
        row("마감 일시", summary.deadline || valueFor("서류일자(=제출일자=입찰일자)"), noteFor("서류일자(=제출일자=입찰일자)")),
        row("제출 방법·제출처", summary.method || valueFor("입찰방식")),
        row("질의응답·설명회 일정", valueFor("제안 발표")),
      ],
    },
    {
      category: "공동수급 의무",
      items: [
        row("컨소시엄 구성 의무·제한", valueFor("공동수급협정서 제출 및 구성방식")),
        row("주관사 지분 요건", ""),
        row("의무 하도급 비율", ""),
      ],
    },
  ];
}

function inferEvaluationMethod(text: string) {
  const labels = [];
  if (text.includes("협상")) {
    labels.push("협상에 의한 계약");
  }
  if (text.includes("적격")) {
    labels.push("적격심사");
  }
  return labels.join(", ");
}

function extractTechPriceRatio(text: string) {
  const match = text.match(/기술(?:능력)?평가\s*(\d+(?:\.\d+)?)\s*(?:점|%)?.*?(?:입찰)?가격평가\s*(\d+(?:\.\d+)?)\s*(?:점|%)?/);
  return match ? `${match[1]}:${match[2]}` : "";
}

function OverviewSubTab({ groups }: { groups: NoticeInfoDetailGroup[] }) {
  return (
    <div className="detailGroupGrid">
      {groups.map((group) => (
        <section className="detailGroup" key={group.category}>
          <h4>{group.category}</h4>
          <div className="infoTable groupedInfoTable">
            {group.items.map((item) => (
              <InfoRow item={item} key={`${group.category}-${item.label}`} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function RequirementsTab({ payload }: { payload: ProposalAnalysisPayload }) {
  const requirements = payload.noticeInfo.requirements;
  const hasCodedRequirements = requirements.some((item) => item.code);
  const requirementGroups = buildRequirementCodeGroups(requirements);
  const requirementTones = buildRequirementTones(requirementGroups);

  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Sheet 2</span>
          <h3>제안요구사항 추출</h3>
          <p>ECR/SFR/PER/IFR/DAR/TER/SER/QUR/COR/PMR/PSR 코드와 요구사항명은 원문 표기 그대로 표시합니다.</p>
        </div>
        <b>{requirements.length}개 요구사항</b>
      </div>

      <div className="requirementsSummary">
        <strong>{requirements.length}개 요구사항</strong>
        <span>{hasCodedRequirements ? "원문 코드 기준" : "코드 미확인 항목 포함"}</span>
      </div>

      <div className="requirementCodeStrip">
        {requirementGroups.map((group) => (
          <span className={`requirementCodeChip reqTone${requirementTones.get(group.prefix) ?? 0}`} key={group.prefix}>
            <strong>{group.prefix}</strong>
            {group.count}개
          </span>
        ))}
      </div>

      <div className="proposalTableWrap">
        <table className="proposalTable requirementsTable">
          <colgroup>
            <col className="requirementCodeCol" />
            <col className="requirementCategoryCol" />
            <col className="requirementNameCol" />
            <col className="requirementTypeCol" />
            <col className="requirementDetailCol" />
          </colgroup>
          <thead>
            <tr>
              <th>코드</th>
              <th>분류</th>
              <th>요구사항명(원문)</th>
              <th>유형</th>
              <th>세부 요구내용 요약</th>
            </tr>
          </thead>
          <tbody>
            {requirements.map((item, index) => (
              <RequirementRow
                item={item}
                index={index}
                tone={requirementTones.get(requirementPrefix(item)) ?? 0}
                key={`${item.code || "no-code"}-${item.requirement}-${index}`}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function requirementPrefix(item: NoticeRequirement) {
  const codePrefix = item.code?.match(/^[A-Za-z]+/)?.[0];
  if (codePrefix) {
    return codePrefix.toUpperCase();
  }
  const categoryPrefix = item.category?.match(/^[A-Za-z]+/)?.[0];
  return categoryPrefix ? categoryPrefix.toUpperCase() : "미분류";
}

function buildRequirementCodeGroups(requirements: NoticeRequirement[]) {
  return requirements.reduce<{ prefix: string; count: number }[]>((groups, item) => {
    const prefix = requirementPrefix(item);
    const existing = groups.find((group) => group.prefix === prefix);
    if (existing) {
      existing.count += 1;
    } else {
      groups.push({ prefix, count: 1 });
    }
    return groups;
  }, []);
}

function buildRequirementTones(groups: { prefix: string; count: number }[]) {
  const tones = new Map<string, number>();
  groups.forEach((group, index) => {
    tones.set(group.prefix, index % 10);
  });
  return tones;
}

function RequirementRow({ item, index, tone }: { item: NoticeRequirement; index: number; tone: number }) {
  const name = item.name || item.requirement;
  const prefix = requirementPrefix(item);

  return (
    <tr className={`requirementToneRow reqTone${tone}`}>
      <td>
        <strong className="requirementCodeText">
          <span>{prefix}</span>
          {item.code || `미확인-${index + 1}`}
        </strong>
      </td>
      <td>{item.category || "-"}</td>
      <td>{name || "-"}</td>
      <td>
        <span className={`requirementBadge ${item.type.includes("필수") ? "required" : ""}`}>{item.type || "확인"}</span>
      </td>
      <td>{item.detail || "-"}</td>
    </tr>
  );
}

function RiskQuestionSubTab({
  risks,
  clarifications,
}: {
  risks: { title: string; detail: string; severity: string }[];
  clarifications: { question: string; reason: string }[];
}) {
  return (
    <div className="riskQuestionGrid">
      <section>
        <h4>놓치기 쉬운 독소조항·특이 요건</h4>
        <div className="riskList">
          {risks.length ? (
            risks.map((item) => (
              <article key={`${item.title}-${item.detail}`}>
                <span>{item.severity || "확인"}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </div>
              </article>
            ))
          ) : (
            <p className="emptySubTabText">공고문상 자동 추출된 특이 요건이 없습니다.</p>
          )}
        </div>
      </section>

      <section>
        <h4>발주처 질의 필요 지점</h4>
        <div className="riskList questionList">
          {clarifications.length ? (
            clarifications.map((item) => (
              <article key={`${item.question}-${item.reason}`}>
                <span>질의</span>
                <div>
                  <strong>{item.question}</strong>
                  <p>{item.reason}</p>
                </div>
              </article>
            ))
          ) : (
            <p className="emptySubTabText">공고문상 불명확으로 표시된 질의 항목이 없습니다.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function InfoRow({ item }: { item: NoticeInfoDetail }) {
  const isDeadline = item.label.includes("서류일자");

  return (
    <article className={isDeadline ? "infoRow deadlineInfoRow" : "infoRow"}>
      <strong>{item.label}</strong>
      <p>{item.value || "-"}</p>
      {item.note ? <span>{item.note}</span> : null}
    </article>
  );
}

function ChecklistTab({ payload }: { payload: ProposalAnalysisPayload }) {
  const storageKey = `proposal-checklist:${payload.id || payload.match.noticeNumber}`;
  const [manualChecks, setManualChecks] = useState<Record<string, boolean>>({});
  const bidNo = payload.match.bidNtceNo || payload.match.noticeNumber.split("-")[0];
  const bidOrd = payload.match.bidNtceOrd || payload.match.noticeNumber.split("-")[1] || "000";

  useEffect(() => {
    let ignore = false;
    const fallbackChecks = (() => {
      try {
        return JSON.parse(localStorage.getItem(storageKey) || "{}") as Record<string, boolean>;
      } catch {
        return {};
      }
    })();
    setManualChecks(fallbackChecks);

    loadChecklistState(bidNo, bidOrd)
      .then((checks) => {
        if (!ignore) {
          setManualChecks(checks);
        }
      })
      .catch(() => {
        if (!ignore) {
          setManualChecks(fallbackChecks);
        }
      });
    return () => {
      ignore = true;
    };
  }, [bidNo, bidOrd, storageKey]);

  const toggleCheck = (key: string, checked: boolean) => {
    const nextChecks = { ...manualChecks, [key]: checked };
    setManualChecks(nextChecks);
    try {
      localStorage.setItem(storageKey, JSON.stringify(nextChecks));
    } catch {
      // local backup is best-effort only.
    }
    saveChecklistState(bidNo, bidOrd, nextChecks).catch(() => {
      // Keep the UI responsive; localStorage remains as a temporary backup if the server is unavailable.
    });
  };

  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Sheet 4</span>
          <h3>{payload.checklist.title}</h3>
          <p>{payload.checklist.method}</p>
        </div>
        <b>{payload.checklist.items.length}건</b>
      </div>

      <div className="proposalTableWrap">
        <table className="proposalTable checklistTable">
          <colgroup>
            <col className="checklistNoCol" />
            <col className="checklistDocCol" />
            <col className="checklistFormCol" />
            <col className="checklistOwnerCol" />
            {payload.checklist.organizationHeaders.map((header) => (
              <col className="checklistOrgCol" key={header} />
            ))}
            <col className="checklistDeadlineCol" />
            <col className="checklistNoteCol" />
            <col className="checklistReadyCol" />
          </colgroup>
          <thead>
            <tr>
              <th>No</th>
              <th>제출서류</th>
              <th>서식</th>
              <th>담당자</th>
              {payload.checklist.organizationHeaders.map((header) => (
                <th key={header}>{header}</th>
              ))}
              <th>마감일</th>
              <th>비고</th>
              <th>구비유무</th>
            </tr>
          </thead>
          <tbody>
            {payload.checklist.items.map((item) => (
              <ChecklistRow
                item={item}
                manualChecks={manualChecks}
                onToggle={toggleCheck}
                key={item.no}
              />
            ))}
          </tbody>
        </table>
      </div>

      {payload.checklist.notes.length ? (
        <div className="proposalNotes">
          {payload.checklist.notes.map((note) => (
            <p className={note.includes("감점") || note.includes("필수") ? "warningNote" : ""} key={note}>
              {note}
            </p>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function checklistCheckKey(item: ProposalChecklistItem) {
  return `${item.no}:${item.document}`;
}

function ChecklistRow({
  item,
  manualChecks,
  onToggle,
}: {
  item: ProposalChecklistItem;
  manualChecks: Record<string, boolean>;
  onToggle: (key: string, checked: boolean) => void;
}) {
  return (
    <tr>
      <td>{item.no}</td>
      <td>
        <strong>{item.document}</strong>
        {item.extra ? <small>{item.extra}</small> : null}
      </td>
      <td>{item.form || "-"}</td>
      <td className={item.owner === "GO" ? "goOwner" : ""}>{item.owner || "-"}</td>
      {item.organizations.map((org) => (
        <td className={!org.required ? "notApplicableCell" : "organizationRequiredCell"} key={org.name}>
          {org.required ? <span>대상</span> : null}
        </td>
      ))}
      <td>{item.deadline || "-"}</td>
      <td>{item.note || "-"}</td>
      <td className="checkCell">
        <label className="manualChecklistCheck">
          <input
            type="checkbox"
            checked={manualChecks[checklistCheckKey(item)] ?? false}
            aria-label={`${item.document} 구비유무`}
            onChange={(event) => onToggle(checklistCheckKey(item), event.target.checked)}
          />
          <span aria-hidden="true" />
        </label>
      </td>
    </tr>
  );
}

function ScoringTab({ payload }: { payload: ProposalAnalysisPayload }) {
  const displayItems = normalizeScoringDisplayItems(payload.scoring.items);
  const scoreGroups = displayItems.reduce<
    { major: string; score: number; items: ProposalScoreItem[]; summary: string }[]
  >((groups, item) => {
    const major = item.major || "기타";
    const existing = groups.find((group) => group.major === major);
    if (existing) {
      existing.score += item.score;
      existing.items.push(item);
    } else {
      groups.push({ major, score: item.score, items: [item], summary: "" });
    }
    return groups;
  }, []).map((group) => ({
    ...group,
    summary: summarizeScoreGroup(group.items),
  }));
  const middleTones = buildScoreMiddleTones(displayItems);

  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Sheet 3</span>
          <h3>{payload.scoring.title}</h3>
          <p>{payload.scoring.totalSummary}</p>
        </div>
        <div className="gradeSummary">
          <span>A {payload.scoring.totals.gradeA}</span>
          <span>B {payload.scoring.totals.gradeB}</span>
          <span>C {payload.scoring.totals.gradeC}</span>
        </div>
      </div>

      <div className="scoreOverviewStrip">
        {scoreGroups.map((group) => (
          <article key={group.major}>
            <span>{group.score}점</span>
            <strong>{group.major}</strong>
            <p>{group.summary}</p>
          </article>
        ))}
      </div>

      <div className="proposalTableWrap">
        <table className="proposalTable scoringTable">
          <colgroup>
            <col className="scoreMajorCol" />
            <col className="scoreMiddleCol" />
            <col className="scoreMinorCol" />
            <col className="scoreNumberCol" />
            <col className="scoreNumberCol" />
            <col className="scoreGradeCol" />
            <col className="scoreStrategyCol" />
            <col className="scoreDetailCol" />
          </colgroup>
          <thead>
            <tr>
              <th>대분류</th>
              <th>중분류</th>
              <th>소분류</th>
              <th>배점</th>
              <th>비중</th>
              <th>등급</th>
              <th>공략 전략</th>
              <th>세부평가내용</th>
            </tr>
          </thead>
          <tbody>
            {displayItems.map((item) => (
              <ScoreRow
                item={item}
                tone={middleTones.get(scoreMiddleKey(item)) ?? 0}
                key={`${item.major}-${item.middle}-${item.minor}`}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function normalizeScoringDisplayItems(items: ProposalScoreItem[]) {
  return items.map((item) => {
    const major = item.major || "";
    const isTopMajor = major.includes("기술") || major.includes("가격");
    if (isTopMajor) {
      return item;
    }
    return {
      ...item,
      major: "기술능력평가",
      middle: item.middle || major,
    };
  });
}

function summarizeScoreGroup(items: ProposalScoreItem[]) {
  const middleScores = items.reduce<{ label: string; score: number }[]>((groups, item) => {
    const label = scoreMiddleKey(item);
    const existing = groups.find((group) => group.label === label);
    if (existing) {
      existing.score += item.score;
    } else {
      groups.push({ label, score: item.score });
    }
    return groups;
  }, []);
  return middleScores.map((item) => `${item.label} ${item.score}점`).join(" · ");
}

function scoreMiddleKey(item: ProposalScoreItem) {
  return item.middle || item.minor || item.major || "기타";
}

function buildScoreMiddleTones(items: ProposalScoreItem[]) {
  const tones = new Map<string, number>();
  items.forEach((item) => {
    const key = scoreMiddleKey(item);
    if (!tones.has(key)) {
      tones.set(key, tones.size % 8);
    }
  });
  return tones;
}

function ScoreRow({ item, tone }: { item: ProposalScoreItem; tone: number }) {
  return (
    <tr className={`scoreToneRow scoreTone${tone}`}>
      <td>{item.major}</td>
      <td>{item.middle || "-"}</td>
      <td>
        <strong>{item.minor}</strong>
      </td>
      <td>{item.score}</td>
      <td>{item.weight}%</td>
      <td>
        <span className={`gradePill gradePill${item.grade}`}>{item.grade || "-"}</span>
      </td>
      <td>{item.strategy}</td>
      <td>{item.detail}</td>
    </tr>
  );
}
