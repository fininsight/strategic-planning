import { useEffect, useMemo, useState } from "react";

import { loadAnalyzerData } from "../../api/analyzerApi";
import { Notice } from "../../types/notice";
import {
  NoticeInfoDetail,
  ProposalAnalysisPayload,
  ProposalChecklistItem,
  ProposalScoreItem,
} from "../../types/analyzer";
import { formatDateTime } from "../../utils/format";

type AnalysisTab = "notice" | "checklist" | "scoring";

const tabs: { id: AnalysisTab; label: string; caption: string }[] = [
  { id: "notice", label: "공고정보", caption: "핵심 정보와 참가요건" },
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
            <p>{payload.noticeInfo.summary.agency}</p>
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

        <section className={selectedNotice ? "matchBanner matched" : "matchBanner"}>
          <div>
            <strong>{selectedNotice ? "선택 공고 매칭" : "분석 JSON"}</strong>
            <p>
              {selectedNotice
                ? `${selectedNotice.number} · ${selectedNotice.title}`
                : "선택된 공고가 없습니다."}
            </p>
          </div>
          <span>{payload.id}</span>
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
  return (
    <div className="proposalSheetGrid">
      <section className="proposalPanel">
        <div className="proposalPanelHeader">
          <div>
            <span>Sheet 1</span>
            <h3>입찰공고 상세</h3>
          </div>
          <b>{payload.noticeInfo.summary.noticeNumber || "공고번호 미확인"}</b>
        </div>
        <div className="infoTable">
          {payload.noticeInfo.details.map((item) => (
            <InfoRow item={item} key={item.label} />
          ))}
        </div>
      </section>

      <section className="proposalPanel">
        <div className="proposalPanelHeader">
          <div>
            <span>참가요건</span>
            <h3>입찰 참가 요건</h3>
          </div>
          <b>{payload.noticeInfo.requirements.length}개 요건</b>
        </div>
        <div className="requirementList">
          {payload.noticeInfo.requirements.map((item) => (
            <article key={`${item.requirement}-${item.type}`}>
              <span className={`requirementBadge ${item.type.includes("필수") ? "required" : ""}`}>{item.type}</span>
              <div>
                <strong>{item.requirement}</strong>
                <p>{item.detail}</p>
              </div>
            </article>
          ))}
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
  return (
    <section className="proposalPanel fullProposalPanel">
      <div className="proposalPanelHeader">
        <div>
          <span>Sheet 2</span>
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
            </tr>
          </thead>
          <tbody>
            {payload.checklist.items.map((item) => (
              <ChecklistRow item={item} key={item.no} />
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

function ChecklistRow({ item }: { item: ProposalChecklistItem }) {
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
        <td className={!org.required ? "notApplicableCell" : ""} key={org.name}>
          {org.required ? <span className={org.checked ? "checkedBox" : "emptyBox"}>{org.checked ? "✓" : "☐"}</span> : null}
        </td>
      ))}
      <td>{item.deadline || "-"}</td>
      <td>{item.note || "-"}</td>
    </tr>
  );
}

function ScoringTab({ payload }: { payload: ProposalAnalysisPayload }) {
  const scoreGroups = payload.scoring.items.reduce<
    { major: string; score: number; items: ProposalScoreItem[] }[]
  >((groups, item) => {
    const major = item.major || "기타";
    const existing = groups.find((group) => group.major === major);
    if (existing) {
      existing.score += item.score;
      existing.items.push(item);
    } else {
      groups.push({ major, score: item.score, items: [item] });
    }
    return groups;
  }, []);

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

      <div className="scoreStrategyGrid">
        {scoreGroups.map((group) => (
          <article key={group.major}>
            <span>{group.score}점</span>
            <strong>{group.major}</strong>
            <p>{group.items.map((item) => item.minor).join(", ")}</p>
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
            {payload.scoring.items.map((item) => (
              <ScoreRow item={item} key={`${item.major}-${item.middle}-${item.minor}`} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ScoreRow({ item }: { item: ProposalScoreItem }) {
  return (
    <tr className={`gradeRow grade${item.grade || "None"}`}>
      <td>{item.major}</td>
      <td>{item.middle}</td>
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
