import { PointerEvent as ReactPointerEvent, useEffect, useState } from "react";

import { loadNoticeAnalysis, loadNoticeDocuments } from "../../api/analysisApi";
import { NoticeAnalysis } from "../../types/analysis";
import { Notice } from "../../types/notice";
import { buildDeepLink, formatBudget, formatDateTime } from "../../utils/format";

type MonitoringPageProps = {
  notice: Notice;
  onBack: () => void;
};

export default function MonitoringPage({ notice, onBack }: MonitoringPageProps) {
  const [apiAnalysis, setApiAnalysis] = useState<NoticeAnalysis | null>(null);
  const [documentPayload, setDocumentPayload] = useState<NoticeAnalysis | null>(null);
  const [documentStatus, setDocumentStatus] = useState<"loading" | "completed" | "failed">("loading");
  const [analysisStatus, setAnalysisStatus] = useState<"loading" | "completed" | "failed">("loading");
  const [analysisError, setAnalysisError] = useState("");
  const [documentError, setDocumentError] = useState("");
  const [activeDocumentId, setActiveDocumentId] = useState("");
  const [splitPercent, setSplitPercent] = useState(60);
  const fallbackAnalysis = buildNoticeAnalysis(notice);
  const bidNo = notice.bidNtceNo || notice.number.split("-")[0];
  const bidOrd = notice.bidNtceOrd || notice.number.split("-")[1] || "000";
  const deepLink = notice.deepLink || buildDeepLink(`${bidNo}-${bidOrd}`);
  const visiblePayload = apiAnalysis ?? documentPayload;
  const analysis = visiblePayload ? buildApiNoticeAnalysis(notice, visiblePayload) : fallbackAnalysis;
  const documents = visiblePayload?.documents ?? [];
  const activeDocument = documents.find((document) => document.id === activeDocumentId) ?? documents[0];
  const activeReport = activeDocument?.analysis;
  const deadline = formatDateTime(notice.closeAt);

  useEffect(() => {
    let ignore = false;

    async function loadDocuments(): Promise<boolean> {
      setDocumentStatus("loading");
      setDocumentError("");
      setDocumentPayload(null);
      try {
        const payload = await loadNoticeDocuments(bidNo, bidOrd);
        if (!ignore) {
          setDocumentPayload(payload);
          setActiveDocumentId(payload.documents?.[0]?.id ?? "");
          setDocumentStatus("completed");
        }
        return true;
      } catch (error) {
        if (!ignore) {
          setDocumentStatus("failed");
          setDocumentError(error instanceof Error ? error.message : "첨부파일을 불러오지 못했습니다.");
        }
        return false;
      }
    }

    async function loadAnalysis() {
      setAnalysisStatus("loading");
      setAnalysisError("");
      try {
        const payload = await loadNoticeAnalysis(bidNo, bidOrd);
        if (!ignore) {
          setApiAnalysis(payload);
          setActiveDocumentId((current) => current || payload.documents?.[0]?.id || "");
          setAnalysisStatus("completed");
        }
      } catch (error) {
        if (!ignore) {
          setApiAnalysis(null);
          setAnalysisStatus("failed");
          setAnalysisError(error instanceof Error ? error.message : "분석 API 호출에 실패했습니다.");
        }
      }
    }

    async function loadInOrder() {
      const ready = await loadDocuments();
      if (ready && !ignore) {
        loadAnalysis();
      } else if (!ignore) {
        setAnalysisStatus("failed");
        setAnalysisError("첨부파일을 먼저 불러오지 못해 분석을 시작하지 않았습니다.");
      }
    }

    loadInOrder();

    return () => {
      ignore = true;
    };
  }, [bidNo, bidOrd]);

  const handleSplitPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const workspace = event.currentTarget.parentElement;
    if (!workspace) return;

    event.currentTarget.setPointerCapture(event.pointerId);
    const rect = workspace.getBoundingClientRect();
    const updateSplit = (clientX: number) => {
      const next = ((clientX - rect.left) / rect.width) * 100;
      setSplitPercent(Math.min(72, Math.max(48, next)));
    };
    const handleMove = (moveEvent: PointerEvent) => updateSplit(moveEvent.clientX);
    const handleUp = () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };

    updateSplit(event.clientX);
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
  };

  return (
    <section className="analysisScreen">
      <header className="analysisHeader">
        <div className="analysisBrand">
          <span className="analysisLogo" aria-hidden="true" />
          <div>
            <h2>공고 상세 분석 및 AI 요약</h2>
            <p>입찰 분석 시스템 v2.0</p>
          </div>
        </div>
        <nav className="analysisNav" aria-label="상세 메뉴">
          {/* <span>홈</span>
          <span>공고 검색</span>
          <strong>AI 분석</strong>
          <span>마이페이지</span> */}
        </nav>
        <div className="analysisActions">
          <a className="deepLinkButton" href={deepLink} target="_blank" rel="noreferrer">
            나라장터 원문
          </a>
          <button className="backToListButton" type="button" onClick={onBack}>
            <span aria-hidden="true" />
            목록으로
          </button>
        </div>
      </header>

      <div
        className="analysisWorkspace"
        style={{ gridTemplateColumns: `${splitPercent}% 10px minmax(340px, 1fr)` }}
      >
        <main className="documentPane">
          <div className="documentToolbar">
            <div className="documentTitle">
              <strong>{notice.title}</strong>
              <span>{notice.number}</span>
            </div>
          </div>

          {documents.length ? (
            <div className="documentTabs" aria-label="첨부 PDF 목록">
              {documents.map((document) => (
                <button
                  className={document.id === activeDocument?.id ? "activeDocumentTab" : ""}
                  type="button"
                  onClick={() => setActiveDocumentId(document.id)}
                  key={document.id}
                >
                  <span>
                    {document.analysis.docType || document.docType} {document.extension}
                  </span>
                  <strong>{document.fileName}</strong>
                </button>
              ))}
            </div>
          ) : null}

          <article className="pdfViewerPane">
            {documentStatus === "loading" ? (
              <div className="analysisLoading">
                <strong>첨부파일 뷰어 준비 중</strong>
                <p>나라장터 첨부파일을 확인하고 있습니다. 분석은 별도로 진행됩니다.</p>
              </div>
            ) : null}
            {documentStatus === "failed" ? (
              <div className="analysisError">
                <strong>첨부파일 로딩 실패</strong>
                <p>{documentError}</p>
                <p>아래 내용은 기존 공고 데이터 기반 미리보기입니다.</p>
              </div>
            ) : null}
            {activeDocument?.viewerType === "pdf" ? (
              <>
                <iframe
                  className="pdfFrame"
                  src={`${activeDocument.fileUrl}#toolbar=1&navpanes=0&view=FitV`}
                  title={activeDocument.fileName}
                />
                {activeDocument.extension !== ".pdf" ? (
                  <div className="convertedNotice">
                    <span>HWP를 PDF로 변환해 표시 중입니다.</span>
                    <a href={activeDocument.originalFileUrl}>원본 다운로드</a>
                  </div>
                ) : null}
              </>
            ) : activeDocument?.viewerType === "text" ? (
              <pre className="textDocumentViewer">{activeDocument.documentText}</pre>
            ) : activeDocument ? (
              <div className="documentEmpty">
                <strong>{activeDocument.fileName}</strong>
                <p>{activeDocument.viewerError || activeDocument.extractionError || "이 파일은 브라우저에서 바로 보기 어렵습니다."}</p>
                <a className="fileDownloadButton" href={activeDocument.originalFileUrl || activeDocument.fileUrl}>
                  파일 다운로드
                </a>
              </div>
            ) : (
              <div className="documentEmpty">
                <strong>{notice.title}</strong>
                <p>분석 API가 연결되면 첨부 PDF 뷰어가 표시됩니다.</p>
              </div>
            )}
          </article>
        </main>

        <button
          className="splitHandle"
          type="button"
          onPointerDown={handleSplitPointerDown}
          aria-label="문서 뷰어와 AI 리포트 비율 조절"
        />

        <aside className="summaryPane">
          <div className="summaryTitleRow">
            <h3>{activeReport ? `${activeReport.docType} AI 리포트` : "AI 요약 리포트"}</h3>
            <span>{activeReport?.analysisSource === "llm" ? "LLM 분석" : analysisStatus === "loading" ? "분석 생성 중" : `매칭률 ${notice.score}%`}</span>
          </div>

          <div className="summaryStatBox">
            <dl>
              <div>
                <dt>사업비</dt>
                <dd>{analysis.budget}</dd>
              </div>
              <div>
                <dt>사업기간</dt>
                <dd>{analysis.period}</dd>
              </div>
              <div>
                <dt>마감일</dt>
                <dd className="deadlineText">{deadline}</dd>
              </div>
            </dl>
          </div>

          {activeDocument ? (
            <section className="summarySection">
              <h4>
                <span className="fileIcon" />
                AI 인사이트 요약{activeDocument.analysis.analysisSource === "llm" ? <em>LLM</em> : null}
              </h4>
              <div className="documentAnalysisBox">
                <span>{activeDocument.analysis.docType || activeDocument.docType}</span>
                <strong>{activeDocument.fileName}</strong>
                <div className="documentMetaLine">
                  <small>{activeDocument.pageCount || "-"}페이지</small>
                  <small>{activeDocument.textLength.toLocaleString("ko-KR")}자 추출</small>
                  <small>{activeDocument.extension}</small>
                </div>
                <p>{activeDocument.analysis.summary}</p>
              </div>
            </section>
          ) : null}

          {activeDocument ? (
            <section className="summarySection">
              <h4>
                <span className="checkIcon" />
                핵심 요구사항
              </h4>
              <div className="checklistBox">
                <ul>
                  {activeDocument.analysis.checklist.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </section>
          ) : null}

          {activeDocument ? (
            <section className="summarySection">
              <h4>배점표 분석</h4>
              <div className="scoreTableBox">
                {activeDocument.analysis.scoreTable.length ? (
                  activeDocument.analysis.scoreTable.map((item) => (
                    <article key={`${item.item}-${item.detail}`}>
                      <b>{item.item}</b>
                      <p>{item.detail}</p>
                    </article>
                  ))
                ) : (
                  <p>이 문서에서 명시적인 배점표나 평가기준을 찾지 못했습니다.</p>
                )}
              </div>
            </section>
          ) : null}

          <section className="summarySection">
            <h4>
              <span className="bulbIcon" />
              공고 전체 인사이트{analysis.insightSource === "llm" ? <em>LLM</em> : null}
            </h4>
            <div className="insightList">
              <article>
                <b className="plusIcon">+</b>
                <div>
                  <strong>강점 분석</strong>
                  <p>{analysis.strength}</p>
                </div>
              </article>
              <article>
                <b className="warningIcon">!</b>
                <div>
                  <strong>잠재적 리스크</strong>
                  <p>{analysis.risk}</p>
                </div>
              </article>
              <article>
                <b className="sparkIcon">✦</b>
                <div>
                  <strong>제안 포인트</strong>
                  <p>{analysis.opportunity}</p>
                </div>
              </article>
            </div>
          </section>

          <section className="summarySection">
            <h4>공고 주요 일정</h4>
            <ol className="timeline">
              {analysis.timeline.map((item, index) => (
                <li className={index > 1 ? "mutedTimeline" : ""} key={`${item.label}-${item.date}`}>
                  <strong>{item.label}</strong>
                  <span>{item.date}</span>
                </li>
              ))}
            </ol>
          </section>

          <div className="summaryFooter">
            <button type="button">
              <span aria-hidden="true" />
              {analysisStatus === "loading" ? "분석 생성 중" : "심층 분석 리포트 생성하기"}
            </button>
            <p>
              {apiAnalysis
                ? `분석 서류 ${documents.length}개 / 현재 ${activeDocument?.extension ?? ".pdf"}`
                : "AI 분석 결과는 내부 검토 참고용입니다."}
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}

function buildNoticeAnalysis(notice: Notice) {
  const cleanTitle = notice.title.replace(/^\[[^\]]+\]\s*/, "");
  const keywords = notice.keywords.length ? notice.keywords.join(", ") : "데이터/AI";
  const hasAi = /AI|인공지능|데이터|빅데이터/i.test(`${notice.title} ${keywords}`);

  return {
    cleanTitle,
    fileName: `${cleanTitle.slice(0, 34)}.pdf`,
    budget: formatBudget(notice.budget),
    period: "공고서 기준 확인",
    scopeIntro: `${notice.agency}에서 발주한 ${cleanTitle} 공고로, ${keywords} 관련 수행 역량과 공공사업 운영 경험을 함께 요구하는 건입니다.`,
    tasks: [
      hasAi ? "AI/데이터 기반 서비스 운영 또는 교육 프로그램 수행" : "공고 목적에 맞춘 용역 수행 계획 수립",
      "사업관리, 일정관리, 산출물 품질관리 체계 제시",
      "수요기관 요구사항에 맞춘 제안서 및 가격입찰 서류 준비",
      "공고서와 제안요청서 기준의 자격, 제출서류, 평가항목 검토",
    ],
    requirements: [
      {
        label: "기술 요건",
        text: notice.industry || "공고서상 요구 업종 및 기술 수행 역량 확인 필요",
      },
      {
        label: "입찰 자격",
        text: `${notice.qualificationSource || "검색조건"} 기준으로 ${notice.matchedCodes.join(", ") || "관련 업종"} 매칭`,
      },
    ],
    strength: `${notice.grade || "분석"}등급, 매칭 점수 ${notice.score}점으로 현재 필터 기준과 부합도가 높습니다. ${notice.reasons?.[0] ?? "핵심 키워드와 업종 조건이 일치합니다."}`,
    risk: `${formatDateTime(notice.closeAt)}까지 제출 준비가 필요합니다. 원본 공고서와 변환 PDF 내용 차이, 제안요청서 별도 요구사항을 확인해야 합니다.`,
    opportunity: "제안요청서의 평가항목을 확인한 뒤 AI/데이터 수행 경험, 공공기관 납품 실적, 일정 대응 방안을 짧고 명확하게 연결하는 전략이 유효합니다.",
    insightSource: "rule" as const,
    timeline: [
      { label: "공고 게시", date: formatDateTime(notice.postedAt) },
      { label: "입찰 서류 제출 마감", date: formatDateTime(notice.closeAt) },
      { label: "평가 및 개찰", date: "공고서 상세 일정 확인" },
    ],
    documentText: "",
  };
}

function buildApiNoticeAnalysis(notice: Notice, apiAnalysis: NoticeAnalysis) {
  const fallback = buildNoticeAnalysis(notice);

  return {
    ...fallback,
    cleanTitle: apiAnalysis.summary.title || fallback.cleanTitle,
    fileName: apiAnalysis.source.fileName || fallback.fileName,
    budget: apiAnalysis.summary.budget || fallback.budget,
    period: "PDF 공고서 기준 확인",
    scopeIntro: apiAnalysis.summary.title
      ? `${apiAnalysis.summary.title} 공고서 PDF 변환본에서 추출한 내용을 기반으로 분석했습니다.`
      : fallback.scopeIntro,
    requirements: apiAnalysis.summary.requirements.length ? apiAnalysis.summary.requirements : fallback.requirements,
    strength: apiAnalysis.summary.strength || fallback.strength,
    risk: apiAnalysis.summary.risk || fallback.risk,
    opportunity: apiAnalysis.summary.opportunity || fallback.opportunity,
    insightSource: apiAnalysis.summary.insightSource || fallback.insightSource,
    timeline: [
      { label: "공고 게시", date: formatDateTime(notice.postedAt) },
      ...apiAnalysis.summary.timeline,
      { label: "대시보드 분석 완료", date: formatDateTime(apiAnalysis.analyzedAt) },
    ],
    documentText: apiAnalysis.documentText,
  };
}
