import { useCallback, useEffect, useState } from "react";
import { RefreshIcon } from "../common/Icons";
import { managerApi } from "../../api/managerApi";
import { ManagerTopNav } from "../layout/ManagerTopNav";
import { ManagerReviewModal } from "./ManagerReviewModal";
import { ManagerAssignmentsView } from "./ManagerAssignmentsView";
import { TeamPerformanceView } from "./TeamPerformanceView";
import { ManagerAccountsView } from "./ManagerAccountsView";

function formatDate(value) {
  return value ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
}

export function ManagerReviewView({ currentUser, onLogout }) {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [overview, setOverview] = useState(null);
  const [queue, setQueue] = useState([]);
  const [history, setHistory] = useState([]);
  const [selectedReview, setSelectedReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overviewData, queueData, historyData] = await Promise.all([
        managerApi.getTeamOverview(), managerApi.getReviewQueue(), managerApi.getManagerHistory({ limit: 50 }),
      ]);
      setOverview(overviewData);
      setQueue(queueData);
      setHistory(historyData);
    } catch (cause) {
      setError(cause.message || "Không thể tải dữ liệu quản lý.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    Promise.all([
      managerApi.getTeamOverview(), managerApi.getReviewQueue(), managerApi.getManagerHistory({ limit: 50 }),
    ]).then(([overviewData, queueData, historyData]) => {
      if (ignore) return;
      setOverview(overviewData);
      setQueue(queueData);
      setHistory(historyData);
    }).catch((cause) => {
      if (!ignore) setError(cause.message || "Không thể tải dữ liệu quản lý.");
    }).finally(() => {
      if (!ignore) setLoading(false);
    });
    return () => { ignore = true; };
  }, []);

  const openReview = async (sessionId) => {
    setError("");
    try {
      setSelectedReview(await managerApi.getReviewDetail(sessionId));
    } catch (cause) {
      setError(cause.message || "Không thể tải chi tiết phiên luyện tập.");
    }
  };

  const approve = async (decision) => {
    if (!selectedReview) return;
    try {
      await managerApi.approveReview(selectedReview.attempt.session_id, decision);
      setSelectedReview(null);
      await load();
    } catch (cause) {
      setError(cause.message || "Không thể duyệt đánh giá. Vui lòng thử lại.");
      throw cause;
    }
  };

  const attempts = activeTab === "reports" ? history : queue;

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
        {activeTab === "assignments" && <ManagerAssignmentsView onNavigateTab={setActiveTab} />}
        {activeTab === "performance" && <TeamPerformanceView onNavigateTab={setActiveTab} />}
        {activeTab === "accounts" && <ManagerAccountsView />}

        {(activeTab === "dashboard" || activeTab === "reports") && (
          <>
            {activeTab === "dashboard" && overview && (
              <div className="manager-console-hero">
                <div className="console-hero-header">
                  <div>
                    <div className="console-tag-badge">VinFast AI Sales Enablement • Trung tâm Quản trị</div>
                    <h1 className="console-hero-title">Tổng quan Năng lực & Đào tạo</h1>
                    <p className="console-hero-desc">
                      Theo dõi thời gian thực kết quả luyện tập của đội ngũ tư vấn viên, phê duyệt đánh giá và phân tích kỹ năng bán xe điện.
                    </p>
                  </div>
                  <div className="console-hero-actions">
                    <button type="button" className="btn-console-sync" onClick={load} disabled={loading}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><RefreshIcon style={{ width: 13, height: 13 }} /> {loading ? "Đang đồng bộ..." : "Đồng bộ số liệu"}</span>
                    </button>
                  </div>
                </div>

                <div className="console-stats-grid" aria-label="Số liệu từ phiên luyện tập">
                  <div className="console-stat-box">
                    <span className="cs-label">Tư vấn viên hoạt động</span>
                    <strong className="cs-val">{overview.active_advisors}</strong>
                    <span className="cs-sub">Đang trong hệ thống</span>
                  </div>
                  <div className="console-stat-box">
                    <span className="cs-label">Phiên hoàn thành</span>
                    <strong className="cs-val">{overview.completed_attempts}</strong>
                    <span className="cs-sub">Tổng số lượt thực chiến</span>
                  </div>
                  <div className="console-stat-box">
                    <span className="cs-label">Đã duyệt đánh giá</span>
                    <strong className="cs-val">{overview.approved_attempts}</strong>
                    <span className="cs-sub">Đạt chuẩn & ghi nhận điểm</span>
                  </div>
                  <div className="console-stat-box">
                    <span className="cs-label">Hàng đợi chờ duyệt</span>
                    <strong className="cs-val" style={{ color: overview.pending_attempts > 0 ? "#FBBF24" : "#FFFFFF" }}>
                      {overview.pending_attempts}
                    </strong>
                    <span className="cs-sub">Cần quản lý phản hồi</span>
                  </div>
                </div>
              </div>
            )}

            <section className="card-white" style={{ padding: 28, marginTop: activeTab === "reports" ? 0 : 8 }}>
              <div className="section-title-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <h2 className="section-heading" style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--primary)" }}>
                  {activeTab === "reports" ? "Lịch sử luyện tập toàn đội ngũ" : "Hàng đợi duyệt đánh giá"}
                </h2>
                <button type="button" className="btn-outline" onClick={load} disabled={loading}>
                  Làm mới
                </button>
              </div>

              {error && (
                <div className="manager-error-alert" role="alert" style={{ color: "#dc2626", marginBottom: 16 }}>
                  {error} <button type="button" className="btn-outline" style={{ marginLeft: 8 }} onClick={load}>Thử lại</button>
                </div>
              )}

              {loading ? (
                <p role="status" style={{ padding: "24px 0", color: "var(--muted)" }}>Đang tải dữ liệu…</p>
              ) : attempts.length === 0 ? (
                <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--muted)", border: "1px dashed var(--border)", borderRadius: "var(--radius-md)" }}>
                  {activeTab === "reports"
                    ? "Chưa có phiên luyện tập nào được hoàn thành."
                    : "Hiện tại không có bài luyện tập nào đang chờ duyệt."}
                </div>
              ) : (
                <div style={{ display: "grid", gap: 12 }}>
                  {attempts.map((attempt) => (
                    <div
                      key={attempt.session_id}
                      className="manager-assignment-card-item"
                    >
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                          <strong style={{ fontSize: "1rem", color: "var(--primary)" }}>
                            {attempt.advisor_id}
                          </strong>
                          <span style={{ fontSize: "0.82rem", color: "var(--muted)" }}>·</span>
                          <span style={{ fontSize: "0.9rem", color: "var(--secondary)" }}>
                            {attempt.scenario_id}
                          </span>
                        </div>
                        <small style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                          {formatDate(attempt.completed_at)} · Trạng thái: <strong>{attempt.review_status}</strong>
                          {attempt.ai_score != null && ` · Điểm AI: ${attempt.ai_score}/3`}
                        </small>
                      </div>
                      <button
                        type="button"
                        className="btn-outline"
                        style={{ padding: "8px 16px", fontSize: "0.85rem", fontWeight: 600 }}
                        onClick={() => openReview(attempt.session_id)}
                      >
                        Xem đánh giá & Duyệt →
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>

      {selectedReview && (
        <ManagerReviewModal
          detail={selectedReview}
          onClose={() => setSelectedReview(null)}
          onApprove={approve}
        />
      )}
    </div>
  );
}
