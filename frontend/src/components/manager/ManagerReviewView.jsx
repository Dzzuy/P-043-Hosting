import { useMemo, useState } from "react";
import { managerApi } from "../../api/managerApi";
import { practiceApi } from "../../api/practiceApi";
import { useLoad } from "../../hooks/useLoad";
import { fmtScore } from "../../utils/scoreFormat";
import { ManagerTopNav } from "../layout/ManagerTopNav";
import { ManagerReviewModal } from "./ManagerReviewModal";
import { ManagerAssignmentsView } from "./ManagerAssignmentsView";
import { ManagerAccountsView } from "./ManagerAccountsView";
import { ManagerDashboard } from "./ManagerDashboard";
import "./managerDashboard.css";

const byOldest = (a, b) => new Date(a.completed_at || 0) - new Date(b.completed_at || 0);

function formatDate(value) {
  return value ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
}

function statusLabel(attempt) {
  if (attempt.review_status === "manager_approved") return "Đã duyệt";
  if (attempt.evaluation_status === "failed") return "Chấm điểm thất bại";
  if (attempt.evaluation_status === "pending") return "Đang chấm điểm";
  return "Chờ duyệt";
}

function HistoryTable({ history, advisorNames, scenarioNames, onOpenReview }) {
  const { status, data, error, reload } = history;
  const rows = data || [];
  return (
    <section className="md-panel" aria-labelledby="md-history-h">
      <div className="md-panel-head">
        <h2 id="md-history-h" className="md-panel-title">Lịch sử luyện tập toàn đội ngũ</h2>
        <button type="button" className="md-btn md-btn--outline" onClick={reload}>Làm mới</button>
      </div>
      {status === "loading" && <p className="md-state" role="status">Đang tải…</p>}
      {status === "error" && (
        <p className="md-state md-state--error" role="alert">
          {error} <button type="button" className="md-link-btn" onClick={reload}>Thử lại</button>
        </p>
      )}
      {status === "ready" && rows.length === 0 && <p className="md-state">Chưa có phiên luyện tập nào được hoàn thành.</p>}
      {status === "ready" && rows.length > 0 && (
        <div className="md-table-scroll">
          <table className="md-queue">
            <thead>
              <tr>
                <th scope="col">Tư vấn viên</th>
                <th scope="col">Tình huống</th>
                <th scope="col">Hoàn thành</th>
                <th scope="col">Trạng thái</th>
                <th scope="col" className="md-right">Điểm</th>
                <th scope="col"><span className="md-sr">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((attempt) => {
                const name = advisorNames[attempt.advisor_id] || attempt.advisor_id;
                const score = attempt.approved_score ?? attempt.ai_score;
                return (
                  <tr key={attempt.session_id}>
                    <td className="md-strong">{name}</td>
                    <td>{scenarioNames[attempt.scenario_id] || attempt.scenario_id}</td>
                    <td className="md-age">{formatDate(attempt.completed_at)}</td>
                    <td>{statusLabel(attempt)}</td>
                    <td className="md-right md-strong">
                      {score == null ? "—" : `${attempt.approved_score == null ? "AI " : ""}${fmtScore(score)} / 3`}
                    </td>
                    <td className="md-right">
                      <button type="button" className="md-btn md-btn--outline" aria-label={`Xem bài của ${name}`} onClick={() => onOpenReview(attempt.session_id)}>
                        {attempt.review_status === "manager_approved" ? "Xem" : "Duyệt"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ManagerReviewView({ currentUser, onLogout }) {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [selected, setSelected] = useState(null);
  const [actionError, setActionError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  const queueLoad = useLoad(() => managerApi.getReviewQueue(), "queue", "Không thể tải hàng đợi duyệt.");
  const historyLoad = useLoad(
    () => (activeTab === "reports" ? managerApi.getManagerHistory({ limit: 50 }) : Promise.resolve([])),
    `history-${activeTab === "reports" ? "on" : "off"}-${refreshToken}`,
    "Không thể tải lịch sử luyện tập.",
  );
  const advisorsLoad = useLoad(() => managerApi.getAdvisors().catch(() => []), "advisors");
  const scenariosLoad = useLoad(() => practiceApi.getScenarios().catch(() => []), "scenarios");

  const queue = useMemo(() => [...(queueLoad.data || [])].sort(byOldest), [queueLoad.data]);
  const advisorNames = useMemo(
    () => Object.fromEntries((advisorsLoad.data || []).map((item) => [item.advisor_id, item.display_name])),
    [advisorsLoad.data],
  );
  const scenarioNames = useMemo(
    () => Object.fromEntries((scenariosLoad.data || []).map((item) => [item.scenario_id, item.title])),
    [scenariosLoad.data],
  );

  const openReview = async (sessionId) => {
    setActionError("");
    try {
      setSelected(await managerApi.getReviewDetail(sessionId));
    } catch (cause) {
      setActionError(cause.message || "Không thể tải chi tiết phiên luyện tập.");
    }
  };

  const currentId = selected?.attempt.session_id;
  const queueIndex = queue.findIndex((item) => item.session_id === currentId);
  const others = queue.filter((item) => item.session_id !== currentId);
  // The next pending review: the one after this in the oldest-first queue, else the first other one.
  const nextId = (queueIndex >= 0 ? queue[queueIndex + 1]?.session_id : undefined) ?? others[0]?.session_id;

  const approve = async (decision) => {
    await managerApi.approveReview(currentId, decision);
    queueLoad.reload();
    setRefreshToken((value) => value + 1);
    if (nextId) await openReview(nextId);
    else setSelected(null);
  };

  const skip = () => {
    if (nextId) openReview(nextId);
  };

  return (
    <div className="manager-app-layout">
      <ManagerTopNav
        activeTab={activeTab}
        onTabChange={setActiveTab}
        currentUser={currentUser}
        pendingCount={queue.length}
        onLogout={onLogout}
      />
      <main className="manager-app-content">
        {actionError && (
          <p className="md-state md-state--error" role="alert">
            {actionError} <button type="button" className="md-link-btn" onClick={() => setActionError("")}>Đóng</button>
          </p>
        )}
        {activeTab === "assignments" && <ManagerAssignmentsView onNavigateTab={setActiveTab} />}
        {activeTab === "accounts" && <ManagerAccountsView />}
        {activeTab === "dashboard" && (
          <ManagerDashboard
            queue={queue}
            queueStatus={queueLoad.status}
            queueError={queueLoad.error}
            onRetryQueue={queueLoad.reload}
            advisorNames={advisorNames}
            scenarioNames={scenarioNames}
            onOpenReview={openReview}
            onNavigateTab={setActiveTab}
            refreshToken={refreshToken}
          />
        )}
        {activeTab === "reports" && (
          <>
            <div className="md-page-head">
              <div>
                <h1>Lịch sử luyện tập</h1>
                <p>Mọi bài luyện của đội ngũ, mới nhất lên trước.</p>
              </div>
            </div>
            <HistoryTable history={historyLoad} advisorNames={advisorNames} scenarioNames={scenarioNames} onOpenReview={openReview} />
          </>
        )}
      </main>

      {selected && (
        <ManagerReviewModal
          detail={selected}
          advisorName={advisorNames[selected.attempt.advisor_id] || selected.attempt.advisor_id}
          scenarioTitle={scenarioNames[selected.attempt.scenario_id] || selected.attempt.scenario_id}
          position={queueIndex >= 0 ? { index: queueIndex + 1, total: queue.length } : null}
          hasNext={Boolean(nextId)}
          onClose={() => setSelected(null)}
          onApprove={approve}
          onSkip={skip}
        />
      )}
    </div>
  );
}
