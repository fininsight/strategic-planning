import { useState } from "react";
import AnalyzerPage from "./pages/analyzer/AnalyzerPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import MonitoringPage from "./pages/monitoring/MonitoringPage";
import { Notice } from "./types/notice";

function App() {
  const [activeTab, setActiveTab] = useState("대시보드");
  const [selectedNotice, setSelectedNotice] = useState<Notice | null>(null);

  const tabs = ["대시보드", "모니터링", "분석", "제안서", "파트너"];

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div>
            <h1>사업제안 에이전트</h1>
            <p>모니터링 시스템</p>
          </div>
        </div>

        <nav className="nav" aria-label="주 메뉴">
          {tabs.map((item, index) => (
            <a
              className={`navItem ${activeTab === item ? "active" : ""}`}
              href="#"
              key={item}
              onClick={(e) => {
                e.preventDefault();
                setActiveTab(item);
              }}
            >
              <span className={`navIcon navIcon${index}`} aria-hidden="true" />
              {item}
            </a>
          ))}
        </nav>

        <div className="profile">
          <div className="avatar" aria-hidden="true">
            관
          </div>
          <div>
            <strong>관리자 모드</strong>
            <span>admin@company.com</span>
          </div>
        </div>
      </aside>

      <main className="appShell">
        {activeTab === "대시보드" && (
          <DashboardPage
            onOpenNotice={(notice) => {
              setSelectedNotice(notice);
              setActiveTab("모니터링");
            }}
          />
        )}
        {activeTab === "모니터링" && selectedNotice && (
          <MonitoringPage
            notice={selectedNotice}
            onBack={() => {
              setActiveTab("대시보드");
            }}
          />
        )}
        {activeTab === "모니터링" && !selectedNotice && (
          <>
            <header className="topbar">
              <div className="titleRow">
                <h2>모니터링</h2>
              </div>
            </header>
            <section className="content">
              <div className="emptyState" style={{ padding: "3rem", textAlign: "center" }}>
                <p>대시보드에서 공고를 선택하면 상세 분석이 표시됩니다.</p>
              </div>
            </section>
          </>
        )}
        {activeTab === "분석" && <AnalyzerPage selectedNotice={selectedNotice} />}
        {activeTab !== "대시보드" && activeTab !== "모니터링" && activeTab !== "분석" && (
          <>
            <header className="topbar">
              <div className="titleRow">
                <h2>{activeTab}</h2>
              </div>
            </header>
            <section className="content">
              <div className="emptyState" style={{ padding: '3rem', textAlign: 'center' }}>
                <p>{activeTab} 탭은 준비 중입니다.</p>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
