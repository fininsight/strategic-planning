import { ChangeEvent, useEffect, useMemo, useState } from "react";

import { loadDashboardData } from "../../api/dashboardApi";
import { BudgetFilter, Notice, SortField, SortOrder } from "../../types/notice";
import { formatDateTime } from "../../utils/format";
import { isBudgetMatched, isSameDate, scanBaseDate, uniqueValues } from "../../utils/filters";
import { compareNotices } from "../../utils/sorting";

const PAGE_SIZE = 10;

type DashboardProps = {
  onOpenNotice?: (notice: Notice) => void;
};

export default function DashboardPage({ onOpenNotice }: DashboardProps) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const [generatedAt, setGeneratedAt] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [search, setSearch] = useState("");
  const [region, setRegion] = useState("all");
  const [industry, setIndustry] = useState("all");
  const [category, setCategory] = useState("all");
  const [grade, setGrade] = useState("all");
  const [method, setMethod] = useState("all");
  const [keyword, setKeyword] = useState("all");
  const [qualificationSource, setQualificationSource] = useState("all");
  const [budget, setBudget] = useState<BudgetFilter>("all");
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let ignore = false;

    async function load() {
      try {
        const payload = await loadDashboardData();
        if (!ignore) {
          setNotices(payload.notices);
          setGeneratedAt(payload.generatedAt ?? "");
          setLoadError("");
        }
      } catch {
        if (!ignore) {
          setNotices([]);
          setGeneratedAt("");
          setLoadError("대시보드 데이터 파일을 읽지 못했습니다.");
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
  }, []);

  const regions = useMemo(() => uniqueValues(notices.map((notice) => notice.region || "전국")).sort(), [notices]);
  const industries = useMemo(() => uniqueValues(notices.map((notice) => notice.industry || "미분류")).sort(), [notices]);
  const categories = useMemo(() => uniqueValues(notices.map((notice) => notice.category || "일반")).sort(), [notices]);
  const grades = useMemo(() => uniqueValues(notices.map((notice) => notice.grade || "미분류")).sort(), [notices]);
  const methods = useMemo(() => uniqueValues(notices.map((notice) => notice.method || "미분류")).sort(), [notices]);
  const keywords = useMemo(() => uniqueValues(notices.flatMap((notice) => notice.keywords ?? [])).sort(), [notices]);
  const qualificationSources = useMemo(
    () => uniqueValues(notices.map((notice) => notice.qualificationSource || "미분류")).sort(),
    [notices],
  );

  const filteredNotices = useMemo(() => {
    const query = search.trim().toLowerCase();

    return notices
      .filter((notice) => {
        const searchable = [
          notice.number,
          notice.title,
          notice.agency,
          notice.region,
          notice.industry,
          notice.method,
          notice.grade,
          notice.qualificationSource,
          ...(notice.matchedCodes ?? []),
          ...(notice.keywords ?? []),
        ]
          .join(" ")
          .toLowerCase();

        return (
          (!query || searchable.includes(query)) &&
          (region === "all" || notice.region === region) &&
          (industry === "all" || notice.industry === industry) &&
          (category === "all" || notice.category === category) &&
          (grade === "all" || notice.grade === grade) &&
          (method === "all" || notice.method === method) &&
          (keyword === "all" || (notice.keywords ?? []).includes(keyword)) &&
          (qualificationSource === "all" || notice.qualificationSource === qualificationSource) &&
          isBudgetMatched(notice, budget)
        );
      })
      .sort((a, b) => compareNotices(a, b, sortField, sortOrder));
  }, [
    budget,
    category,
    grade,
    industry,
    keyword,
    method,
    notices,
    qualificationSource,
    region,
    search,
    sortField,
    sortOrder,
  ]);

  const activeNotices = filteredNotices.filter((notice) => {
    const closeAt = new Date(notice.closeAt);
    return !Number.isNaN(closeAt.getTime()) && closeAt >= new Date();
  });
  const baseDate = scanBaseDate(generatedAt);
  const dueTodayNotices = filteredNotices.filter((notice) => isSameDate(notice.closeAt, baseDate));
  const newTodayNotices = filteredNotices.filter((notice) => isSameDate(notice.postedAt, baseDate));
  const pageCount = Math.max(1, Math.ceil(filteredNotices.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pagedNotices = filteredNotices.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [budget, category, grade, industry, keyword, method, qualificationSource, region, search, sortField, sortOrder]);

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  const handleBudgetChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setBudget(event.target.value as BudgetFilter);
  };

  return (
    <>
      <header className="topbar">
        <div className="titleRow">
          <span className="filterMark" aria-hidden="true" />
          <h2>나라장터 모니터링 및 필터링</h2>
        </div>

        <div className="topActions">
          <label className="searchBox">
            <span className="searchIcon" aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="공고 번호 또는 키워드 검색"
            />
          </label>
          <button className="iconButton" type="button" aria-label="알림">
            <span className="bellIcon" />
            <i />
          </button>
          <button className="iconButton" type="button" aria-label="설정">
            <span className="gearIcon" />
          </button>
        </div>
      </header>

      <section className="content">
        <section className="summaryGrid" aria-label="공고 요약">
          <MetricCard label="키워드 매칭 공고" value={`${filteredNotices.length}건`} trend="↗5%" tone="positive" icon="key" />
          <MetricCard label="오늘 마감" value={`${dueTodayNotices.length}건`} trend="↘2%" tone="negative" icon="clock" />
          <MetricCard label="오늘 신규" value={`${newTodayNotices.length}건`} trend="↗10%" tone="positive" icon="new" />
          <MetricCard label="진행 중인 입찰" value={`${activeNotices.length}건`} trend="유지" tone="muted" icon="calendar" />
        </section>

        <section className="toolbar" aria-label="공고 필터">
          <div className="filterGroup">
            <label>
              지역:
              <select value={region} onChange={(event) => setRegion(event.target.value)}>
                <option value="all">전체</option>
                {regions.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              업종:
              <select value={industry} onChange={(event) => setIndustry(event.target.value)}>
                <option value="all">전체</option>
                {industries.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              예산:
              <select value={budget} onChange={handleBudgetChange}>
                <option value="all">전체</option>
                <option value="under100m">1억 미만</option>
                <option value="100mTo300m">1억 이상 3억 미만</option>
                <option value="over300m">3억 이상</option>
              </select>
            </label>
            <label>
              분류:
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                <option value="all">전체</option>
                {categories.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              등급:
              <select value={grade} onChange={(event) => setGrade(event.target.value)}>
                <option value="all">전체</option>
                {grades.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              방식:
              <select value={method} onChange={(event) => setMethod(event.target.value)}>
                <option value="all">전체</option>
                {methods.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              키워드:
              <select value={keyword} onChange={(event) => setKeyword(event.target.value)}>
                <option value="all">전체</option>
                {keywords.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              출처:
              <select value={qualificationSource} onChange={(event) => setQualificationSource(event.target.value)}>
                <option value="all">전체</option>
                {qualificationSources.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              정렬:
              <select value={sortField} onChange={(event) => setSortField(event.target.value as SortField)}>
                <option value="score">점수</option>
                <option value="closeAt">마감일</option>
                <option value="postedAt">공고일</option>
                <option value="budget">예산</option>
                <option value="title">공고명</option>
              </select>
            </label>
            <label>
              순서:
              <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as SortOrder)}>
                <option value="desc">내림차순</option>
                <option value="asc">오름차순</option>
              </select>
            </label>
          </div>
          <p className="lastUpdated">마지막 업데이트: {generatedAt ? formatDateTime(generatedAt) : "-"}</p>
        </section>

        <section className="g2bPanel" aria-label="나라장터 검색 결과">
          <BrowserBar />
          <div className="g2bHeader">
            <strong>나라장터</strong>
            <span>국가종합전자조달</span>
            <nav aria-label="나라장터 메뉴">
              <a href="#">입찰정보</a>
              <a href="#">계약현황</a>
              <a href="#">카탈로그</a>
              <a href="#">공동조달</a>
              <a href="#">고객센터</a>
            </nav>
          </div>

          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>업무</th>
                  <th>공고번호-차수</th>
                  <th>분류</th>
                  <th>공고명</th>
                  <th>공고기관</th>
                  <th>마감일시</th>
                  <th>점수</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td className="emptyState" colSpan={7}>
                      공고 데이터를 불러오는 중입니다.
                    </td>
                  </tr>
                ) : loadError ? (
                  <tr>
                    <td className="emptyState" colSpan={7}>
                      {loadError}
                    </td>
                  </tr>
                ) : filteredNotices.length ? (
                  pagedNotices.map((notice) => (
                    <NoticeRow notice={notice} onSelect={onOpenNotice} key={notice.number} />
                  ))
                ) : (
                  <tr>
                    <td className="emptyState" colSpan={7}>
                      표시할 공고가 없습니다. 스캐너를 실행하면 데이터가 채워집니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            {!isLoading && !loadError && filteredNotices.length > 0 ? (
              <div className="pagination" aria-label="페이지네이션">
                <p>
                  총 {filteredNotices.length}건 중 {(currentPage - 1) * PAGE_SIZE + 1}-
                  {Math.min(currentPage * PAGE_SIZE, filteredNotices.length)}건 표시
                </p>
                <div className="pageControls">
                  <button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage === 1}>
                    이전
                  </button>
                  {Array.from({ length: pageCount }, (_, index) => index + 1).map((pageNumber) => (
                    <button
                      className={pageNumber === currentPage ? "activePage" : ""}
                      type="button"
                      onClick={() => setPage(pageNumber)}
                      key={pageNumber}
                    >
                      {pageNumber}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
                    disabled={currentPage === pageCount}
                  >
                    다음
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </section>
    </>
  );
}

function MetricCard({
  label,
  value,
  trend,
  tone,
  icon,
}: {
  label: string;
  value: string;
  trend: string;
  tone: "positive" | "negative" | "muted";
  icon: "key" | "clock" | "new" | "calendar";
}) {
  return (
    <article className="metric">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <b className={`trend ${tone}`}>{trend}</b>
      <span className={`metricIcon ${icon}`} aria-hidden="true">
        {icon === "new" ? "NEW" : ""}
      </span>
    </article>
  );
}

function BrowserBar() {
  return (
    <div className="browserBar">
      <div className="trafficLights" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="address">
        <span className="lock" />
        https://www.g2b.go.kr
      </div>
      <button className="refreshButton" type="button" aria-label="새로고침" />
      <button className="menuButton" type="button" aria-label="더보기" />
    </div>
  );
}

function NoticeRow({ notice, onSelect }: { notice: Notice; onSelect?: (notice: Notice) => void }) {
  const isUrgent = isSameDate(notice.closeAt);

  return (
    <tr>
      <td>
        <span className="badgeStack">
          {notice.task.split("").map((letter) => (
            <span className="badge" key={letter}>
              {letter}
            </span>
          ))}
        </span>
      </td>
      <td>{notice.number}</td>
      <td>
        <span className="category">{notice.category}</span>
      </td>
      <td>
        <button className="noticeTitle noticeTitleButton" type="button" onClick={() => onSelect?.(notice)}>
          {notice.title}
        </button>
        <div className="noticeMeta">
          <span>{notice.grade || "-"}</span>
          <span>{notice.industry || "미분류"}</span>
          <span>{notice.method || "미분류"}</span>
        </div>
      </td>
      <td>{notice.agency}</td>
      <td className={isUrgent ? "urgent" : ""}>{isUrgent ? "오늘마감 17:00" : formatDateTime(notice.closeAt)}</td>
      <td>
        <span className="score">{notice.score}</span>
      </td>
    </tr>
  );
}
