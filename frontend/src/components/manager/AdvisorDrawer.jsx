import { useMemo } from 'react';
import { X } from 'lucide-react';
import { managerApi } from '../../api/managerApi';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { useLoad } from '../../hooks/useLoad';
import { CRITERIA, daysSince, fmtDayMonth, fmtDelta, fmtScore, initialsOf, sparkPoints } from '../../utils/scoreFormat';

const ATTEMPT_LIMIT = 12;
const DAY = 86400000;

function Sparkline({ values, label, tone }) {
  const runs = sparkPoints(values, 150, 32, 3);
  const dots = runs.flat();
  return (
    <svg role="img" aria-label={label} viewBox="0 0 150 32" className={`md-spark md-spark--${tone}`}>
      <line x1="0" y1="16" x2="150" y2="16" className="md-spark-mid" />
      {runs.map((run) => (
        run.length > 1
          ? <polyline key={`${run[0].x}-${run.length}`} fill="none" points={run.map((point) => `${point.x},${point.y}`).join(' ')} />
          : null
      ))}
      {dots.length === 1 && <circle cx={dots[0].x} cy={dots[0].y} r="3" />}
    </svg>
  );
}

function statusLine(item) {
  if (item.review_status === 'manager_approved') return `Đã duyệt ${fmtDayMonth(item.completed_at)}`;
  if (item.evaluation_status === 'failed') return 'Chấm điểm thất bại';
  const days = daysSince(item.completed_at);
  if (days == null) return 'Chờ duyệt';
  return `Chờ duyệt, hoàn thành ${days === 0 ? 'hôm nay' : `${days} ngày trước`}`;
}

/** Per-criterion approved scores, oldest first, from the advisor's approved attempts. */
async function loadSeries(advisorId) {
  const attempts = await managerApi.getAttempts({ advisorId, limit: ATTEMPT_LIMIT });
  const approved = attempts
    .filter((item) => item.review_status === 'manager_approved')
    .sort((a, b) => new Date(a.completed_at) - new Date(b.completed_at));
  const details = await Promise.allSettled(approved.map((item) => managerApi.getReviewDetail(item.session_id)));
  const series = Object.fromEntries(CRITERIA.map((item) => [item.key, []]));
  details.forEach((outcome, index) => {
    if (outcome.status !== 'fulfilled') return;
    const result = outcome.value.manager_review?.approved_result;
    const when = new Date(approved[index].completed_at).getTime();
    (result?.evaluations || []).forEach((evaluation) => {
      if (evaluation.status === 'assessed' && series[evaluation.criterion]) {
        series[evaluation.criterion].push({ score: evaluation.score, when });
      }
    });
  });
  return { attempts, series };
}

function change4w(points) {
  const now = Date.now();
  const recent = points.filter((point) => now - point.when <= 28 * DAY).map((point) => point.score);
  const before = points.filter((point) => now - point.when > 28 * DAY && now - point.when <= 56 * DAY).map((point) => point.score);
  if (recent.length === 0 || before.length === 0) return null;
  const mean = (list) => list.reduce((sum, value) => sum + value, 0) / list.length;
  return mean(recent) - mean(before);
}

export function AdvisorDrawer({ row, trend, scenarioNames, onClose, onOpenReview }) {
  const { ref, onKeyDown } = useDialogFocus(onClose);
  const data = useLoad(() => loadSeries(row.advisor_id), `advisor-${row.advisor_id}`, 'Không thể tải chi tiết tư vấn viên.');
  const recent = useMemo(
    () => [...(data.data?.attempts || [])].sort((a, b) => new Date(b.completed_at || 0) - new Date(a.completed_at || 0)).slice(0, 5),
    [data.data],
  );
  const weekly = trend.map((item) => item.avg_score);
  const weeklyFilled = weekly.filter((value) => value != null);

  return (
    <div className="md-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside
        ref={ref}
        tabIndex={-1}
        className="md-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="md-drawer-h"
        onKeyDown={onKeyDown}
      >
        <header className="md-drawer-head">
          <span className="md-drawer-avatar" aria-hidden="true">{initialsOf(row.display_name)}</span>
          <div className="md-drawer-title">
            <h2 id="md-drawer-h">{row.display_name}</h2>
            <p>
              {row.approved_sessions} bài đã duyệt
              {row.overall_avg != null && `, điểm trung bình ${fmtScore(row.overall_avg, 2)} / 3`}
            </p>
          </div>
          <button type="button" className="md-close" aria-label="Đóng" onClick={onClose}><X size={18} aria-hidden="true" /></button>
        </header>

        <div className="md-drawer-body">
          <section aria-labelledby="md-drawer-skills">
            <h3 id="md-drawer-skills">Từng kỹ năng qua các bài</h3>
            {data.status === 'loading' && <p className="md-state" role="status">Đang tải…</p>}
            {data.status === 'error' && (
              <p className="md-state md-state--error" role="alert">
                {data.error} <button type="button" className="md-link-btn" onClick={data.reload}>Thử lại</button>
              </p>
            )}
            {data.status === 'ready' && (
              <>
                <ul className="md-skill-list">
                  {weeklyFilled.length > 0 && (
                    <li>
                      <span>Điểm tổng theo tuần</span>
                      <Sparkline values={weekly} tone="up" label={`Điểm tổng theo tuần: ${weeklyFilled.map((value) => fmtScore(value)).join(', ')}`} />
                      <strong>{fmtScore(weeklyFilled[weeklyFilled.length - 1])}</strong>
                      <span className="md-skill-delta">{weeklyFilled.length > 1 ? fmtDelta(weeklyFilled[weeklyFilled.length - 1] - weeklyFilled[0]) : '—'}</span>
                    </li>
                  )}
                  {CRITERIA.map((criterion) => {
                    const points = data.data.series[criterion.key];
                    const values = points.map((point) => point.score);
                    const delta = change4w(points);
                    const cell = row.criteria?.[criterion.key];
                    return (
                      <li key={criterion.key}>
                        <span>{criterion.label}</span>
                        {values.length > 0
                          ? <Sparkline values={values} tone={delta != null && delta < 0 ? 'down' : 'up'} label={`${criterion.label}: ${values.join(', ')}`} />
                          : <span className="md-spark-empty">Chưa có điểm</span>}
                        <strong>{fmtScore(cell?.avg)}</strong>
                        <span className={delta != null && delta < 0 ? 'md-skill-delta md-skill-delta--down' : 'md-skill-delta'}>{fmtDelta(delta)}</span>
                      </li>
                    );
                  })}
                </ul>
                <p className="md-drawer-foot">Đường giữa là mức 2 (chuẩn chuyên nghiệp). Cột cuối: thay đổi so với 4 tuần trước.</p>
              </>
            )}
          </section>

          <section aria-labelledby="md-drawer-recent">
            <h3 id="md-drawer-recent">Bài gần đây</h3>
            {data.status === 'ready' && recent.length === 0 && <p className="md-state">Chưa có bài luyện nào.</p>}
            <ul className="md-recent">
              {recent.map((item) => (
                <li key={item.session_id}>
                  <button type="button" onClick={() => onOpenReview(item.session_id)}>
                    <span className="md-recent-main">
                      <span className="md-recent-title">{scenarioNames[item.scenario_id] || item.scenario_id}</span>
                      <span className="md-recent-meta">{statusLine(item)}</span>
                    </span>
                    <strong>
                      {item.approved_score != null ? `${fmtScore(item.approved_score)} / 3` : (item.ai_score != null ? `AI ${fmtScore(item.ai_score)}` : '—')}
                    </strong>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </aside>
    </div>
  );
}
