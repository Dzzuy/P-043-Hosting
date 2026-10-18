import { fmtDayMonth, fmtScore } from '../../utils/scoreFormat';
import './advisorProgress.css';

const LIMIT = 10;

function statusOf(item) {
  if (item.review_status === 'manager_approved') return { text: 'Đã duyệt', ok: true };
  if (item.evaluation_status === 'failed') return { text: 'Chấm điểm thất bại', ok: false };
  if (item.evaluation_status === 'pending') return { text: 'Đang chấm điểm', ok: false };
  return { text: 'Chờ quản lý duyệt', ok: false };
}

export function PracticeHistory({ history, status, error, onRetry, onSelectSession, scenarioNames }) {
  const rows = [...history]
    .sort((a, b) => new Date(b.completed_at || b.started_at || 0) - new Date(a.completed_at || a.started_at || 0))
    .slice(0, LIMIT);
  return (
    <section className="ap-card ap-card--wide" aria-labelledby="ap-history-h">
      <div className="ap-card-head">
        <h2 id="ap-history-h">Lịch sử luyện tập</h2>
        <span className="ap-hint">Bấm một bài để xem lại hội thoại và nhận xét.</span>
      </div>
      {status === 'loading' && <p className="ap-state" role="status">Đang tải lịch sử…</p>}
      {status === 'error' && (
        <p className="ap-state ap-state--error" role="alert">
          Không tải được lịch sử: {error || 'Vui lòng thử lại.'} <button type="button" className="ap-link" onClick={onRetry}>Thử lại</button>
        </p>
      )}
      {status === 'ready' && rows.length === 0 && <p className="ap-state">Chưa có phiên luyện tập nào hoàn tất.</p>}
      {status === 'ready' && rows.length > 0 && (
        <ul className="ap-history">
          {rows.map((item) => {
            const state = statusOf(item);
            const score = item.approved_score ?? item.ai_score;
            return (
              <li key={item.session_id}>
                <button type="button" onClick={() => onSelectSession(item.session_id)}>
                  <span className="ap-history-main">
                    <span className="ap-history-title">{scenarioNames[item.scenario_id] || item.scenario_id}</span>
                    <span className="ap-history-meta">{fmtDayMonth(item.completed_at || item.started_at)}{state.ok ? ', đã duyệt' : `, ${state.text.toLowerCase()}`}</span>
                  </span>
                  <span className={state.ok ? 'ap-history-status ap-history-status--ok' : 'ap-history-status'}>{state.text}</span>
                  <strong className="ap-history-score">
                    {score == null ? '—' : (item.approved_score == null ? `AI ${fmtScore(score)}` : `${fmtScore(score)} / 3`)}
                  </strong>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
