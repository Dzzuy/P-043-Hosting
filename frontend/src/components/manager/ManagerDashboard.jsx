import { useState } from 'react';
import { Plus } from 'lucide-react';
import { managerApi } from '../../api/managerApi';
import { useLoad } from '../../hooks/useLoad';
import { CRITERIA, CRITERION_LABEL, daysSince, fmtScore } from '../../utils/scoreFormat';
import { AdvisorDrawer } from './AdvisorDrawer';
import './managerDashboard.css';

const WEEKS = 8;

function heatClass(cell) {
  if (!cell || cell.insufficient) return 'md-cell--none';
  if (cell.avg == null) return 'md-cell--none';
  if (cell.avg < 1.7) return 'md-cell--low';
  if (cell.avg < 2.3) return 'md-cell--mid';
  if (cell.avg < 2.7) return 'md-cell--good';
  return 'md-cell--top';
}

function PanelState({ status, error, onRetry, empty, emptyText, children }) {
  if (status === 'loading') return <p className="md-state" role="status">Đang tải…</p>;
  if (status === 'error') {
    return (
      <p className="md-state md-state--error" role="alert">
        {error || 'Không thể tải dữ liệu.'}
        {onRetry && <button type="button" className="md-link-btn" onClick={onRetry}>Thử lại</button>}
      </p>
    );
  }
  if (empty) return <p className="md-state">{emptyText}</p>;
  return children;
}

function dayLabel(days) {
  if (days == null) return '';
  if (days === 0) return 'Hôm nay';
  if (days === 1) return 'Hôm qua';
  return `Đợi ${days} ngày`;
}

function TodayStrip({ dashboard, oldestId, onOpenReview, onNavigateTab }) {
  const pending = dashboard.queue?.pending ?? 0;
  const overdue = dashboard.assignments?.overdue ?? [];
  if (pending === 0 && overdue.length === 0) return null;
  const oldestDays = daysSince(dashboard.queue?.oldest_pending_at);
  const names = [...new Set(overdue.map((item) => item.advisor_name))];
  return (
    <section className="md-today" aria-labelledby="md-today-h">
      <h2 id="md-today-h">Cần xử lý hôm nay</h2>
      {pending > 0 && (
        <div className="md-today-item">
          <strong>{pending}</strong>
          <span>
            bài chờ duyệt{oldestDays != null && (oldestDays === 0 ? ', bài cũ nhất mới hoàn thành hôm nay' : `, bài cũ nhất đã đợi ${oldestDays} ngày`)}
          </span>
        </div>
      )}
      {overdue.length > 0 && (
        <div className="md-today-item md-today-item--warn">
          <strong>{overdue.length}</strong>
          <span>bài giao quá hạn: {names.join(', ')}</span>
        </div>
      )}
      <div className="md-today-actions">
        {pending > 0 && oldestId && (
          <button type="button" className="md-btn md-btn--primary" onClick={() => onOpenReview(oldestId)}>Duyệt bài cũ nhất</button>
        )}
        {overdue.length > 0 && (
          <button type="button" className="md-btn md-btn--ghost-dark" onClick={() => onNavigateTab('assignments')}>Xem bài giao</button>
        )}
      </div>
    </section>
  );
}

function SkillHeatmap({ rows, onOpenAdvisor }) {
  return (
    <>
      <div className="md-table-scroll">
        <table className="md-heatmap">
          <thead>
            <tr>
              <th scope="col" className="md-heatmap-name">Tư vấn viên</th>
              {CRITERIA.map((item) => <th scope="col" key={item.key}>{item.label}</th>)}
              <th scope="col" className="md-heatmap-avg">Trung bình</th>
              <th scope="col">Bài đã duyệt</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.advisor_id}>
                <th scope="row" className="md-heatmap-name">
                  <button type="button" className="md-row-btn" onClick={() => onOpenAdvisor(row)}>
                    {row.display_name}
                  </button>
                  {row.approved_sessions < 2 && (
                    <span className="md-row-note">{row.approved_sessions === 0 ? 'Chưa có bài được duyệt' : `Mới vào, ${row.approved_sessions} bài`}</span>
                  )}
                </th>
                {CRITERIA.map((item) => {
                  const cell = row.criteria?.[item.key];
                  return (
                    <td key={item.key} className={`md-cell ${heatClass(cell)}`}>
                      <span className="md-sr">{item.label}: </span>
                      {fmtScore(cell?.avg)}
                      {cell?.insufficient && <span className="md-sr"> (chưa đủ dữ liệu)</span>}
                    </td>
                  );
                })}
                <td className="md-heatmap-avg-val">{fmtScore(row.overall_avg, 2)}</td>
                <td className="md-heatmap-n">{row.approved_sessions}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="md-legend" aria-label="Chú giải màu">
        <li><i className="md-swatch md-cell--low" />Cần kèm (dưới 1,7)</li>
        <li><i className="md-swatch md-cell--mid" />Đạt chuẩn (1,7 đến 2,3)</li>
        <li><i className="md-swatch md-cell--good" />Tốt (2,3 đến 2,7)</li>
        <li><i className="md-swatch md-cell--top" />Xuất sắc (từ 2,7)</li>
        <li><i className="md-swatch md-cell--none" />Chưa đủ dữ liệu (dưới 2 lượt chấm)</li>
      </ul>
    </>
  );
}

// Open items first, done items sink to the bottom; the sort is stable so order within each group is kept.
const openFirst = (list) => [...(list || [])].sort((a, b) => Number(a.done) - Number(b.done));

function Todos() {
  const todos = useLoad(() => managerApi.getTodos(), 'todos', 'Không thể tải việc cần làm.');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const items = todos.data || [];

  const add = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setActionError('');
    try {
      const created = await managerApi.createTodo(text);
      todos.setData((current) => openFirst([created, ...(current || [])]));
      setDraft('');
    } catch (cause) {
      setActionError(cause.message || 'Không thể thêm việc.');
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (item) => {
    const next = !item.done;
    setActionError('');
    todos.setData((current) => openFirst((current || []).map((entry) => (entry.todo_id === item.todo_id ? { ...entry, done: next } : entry))));
    try {
      const saved = await managerApi.setTodoDone(item.todo_id, next);
      todos.setData((current) => (current || []).map((entry) => (entry.todo_id === item.todo_id ? { ...entry, ...saved } : entry)));
    } catch (cause) {
      todos.setData((current) => openFirst((current || []).map((entry) => (entry.todo_id === item.todo_id ? { ...entry, done: item.done } : entry))));
      setActionError(cause.message || 'Không thể cập nhật việc.');
    }
  };

  return (
    <section className="md-panel md-todos" aria-labelledby="md-todos-h">
      <h2 id="md-todos-h" className="md-panel-title">Việc cần làm</h2>
      <form className="md-todo-form" onSubmit={add}>
        <label htmlFor="md-todo-new" className="md-sr">Thêm việc</label>
        <input
          id="md-todo-new"
          type="text"
          maxLength={300}
          placeholder="Thêm việc cần làm"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" className="md-icon-btn" aria-label="Thêm việc" disabled={busy || !draft.trim()}>
          <Plus size={18} strokeWidth={2.4} aria-hidden="true" />
        </button>
      </form>
      {actionError && <p className="md-state md-state--error" role="alert">{actionError}</p>}
      <PanelState status={todos.status} error={todos.error} onRetry={todos.reload} empty={items.length === 0} emptyText="Chưa có việc nào. Thêm việc đầu tiên ở ô phía trên.">
        <ul className="md-todo-list">
          {items.map((item) => (
            <li key={item.todo_id}>
              <label className={item.done ? 'md-todo md-todo--done' : 'md-todo'}>
                <input type="checkbox" checked={Boolean(item.done)} onChange={() => toggle(item)} />
                <span>{item.text}</span>
              </label>
            </li>
          ))}
        </ul>
      </PanelState>
    </section>
  );
}

function runsOf(points) {
  const runs = [];
  let run = [];
  points.forEach((point) => {
    if (point.y == null) {
      if (run.length) runs.push(run);
      run = [];
    } else run.push(point);
  });
  if (run.length) runs.push(run);
  return runs;
}

function TeamTrend({ trend }) {
  const left = 56;
  const right = 704;
  const count = trend.length;
  const xAt = (index) => (count === 1 ? (left + right) / 2 : left + (index * (right - left)) / (count - 1));
  const yAt = (value) => 220 - (Math.min(3, Math.max(1, value)) - 1) * 100;
  const points = trend.map((item, index) => ({ x: xAt(index), y: item.avg_score == null ? null : yAt(item.avg_score), value: item.avg_score }));
  const filled = points.filter((point) => point.y != null);
  const first = filled[0];
  const last = filled[filled.length - 1];
  const summary = filled.length >= 2
    ? `Điểm trung bình của đội đi từ ${fmtScore(first.value, 2)} ở tuần đầu đến ${fmtScore(last.value, 2)} ở tuần gần nhất.`
    : 'Chưa đủ tuần có dữ liệu để vẽ xu hướng.';
  return (
    <figure className="md-trend">
      <svg role="img" aria-label={summary} viewBox="0 0 720 250">
        <g className="md-svg-axis">
          <text x="0" y="24">3,0</text><text x="0" y="124">2,0</text><text x="0" y="224">1,0</text>
        </g>
        <line x1="40" y1="20" x2="712" y2="20" className="md-svg-grid" />
        <line x1="40" y1="220" x2="712" y2="220" className="md-svg-base" />
        <line x1="40" y1="120" x2="712" y2="120" className="md-svg-ref" />
        <text x="712" y="114" textAnchor="end" className="md-svg-axis-text">Chuẩn chuyên nghiệp (2)</text>
        {runsOf(points).map((run) => (
          <polyline key={`${run[0].x}`} className="md-svg-line" fill="none" points={run.map((point) => `${point.x},${point.y}`).join(' ')} />
        ))}
        {filled.map((point, index) => (
          <circle key={point.x} cx={point.x} cy={point.y} r={index === filled.length - 1 ? 5 : 4} className="md-svg-dot" />
        ))}
        {last && <text x={last.x} y={last.y - 11} textAnchor="end" className="md-svg-value">{fmtScore(last.value, 2)}</text>}
        <g className="md-svg-axis-text" textAnchor="middle">
          {trend.map((item, index) => <text key={item.week_start} x={xAt(index)} y="244">T{index + 1}</text>)}
        </g>
      </svg>
      <figcaption>Số bài mỗi tuần: {trend.map((item) => item.attempts).join(', ')}.</figcaption>
    </figure>
  );
}

function AiAgreement({ items, approved }) {
  const ordered = CRITERIA.map((criterion) => items.find((item) => item.criterion === criterion.key) || { criterion: criterion.key, reviewed: 0, changed: 0, changed_rate: 0, mean_delta: 0 });
  const max = Math.max(...ordered.map((item) => item.changed_rate || 0));
  const top = max > 0 ? ordered.find((item) => (item.changed_rate || 0) === max) : null;
  const delta = top ? Math.abs(top.mean_delta || 0) : 0;
  return (
    <>
      <p className="md-panel-sub">Tỷ lệ bài quản lý đã sửa điểm AI, trên {approved} bài đã duyệt.</p>
      <ul className="md-agree">
        {ordered.map((item) => {
          const rate = item.changed_rate || 0;
          return (
            <li key={item.criterion}>
              <span>{CRITERION_LABEL[item.criterion] || item.criterion}</span>
              <span className="md-agree-track" aria-hidden="true">
                <span className={top && item === top ? 'md-agree-bar md-agree-bar--max' : 'md-agree-bar'} style={{ width: max > 0 ? `${Math.round((rate / max) * 100)}%` : '0%' }} />
              </span>
              <strong>{Math.round(rate * 100)}%</strong>
            </li>
          );
        })}
      </ul>
      {top && (
        <p className="md-agree-note">
          {CRITERION_LABEL[top.criterion]} bị sửa nhiều nhất ({top.changed}/{top.reviewed} bài)
          {delta > 0 && `. Ở các bài bị sửa, điểm AI ${top.mean_delta > 0 ? 'cao' : 'thấp'} hơn điểm quản lý trung bình ${fmtScore(delta)} điểm`}.
        </p>
      )}
    </>
  );
}

function ReviewQueue({ queue, status, error, onRetry, advisorNames, scenarioNames, onOpenReview }) {
  const sorted = [...queue].sort((a, b) => new Date(a.completed_at || 0) - new Date(b.completed_at || 0));
  return (
    <section className="md-panel" aria-labelledby="md-queue-h">
      <div className="md-panel-head">
        <h2 id="md-queue-h" className="md-panel-title">Hàng đợi duyệt</h2>
        <span className="md-panel-hint">Cũ nhất lên trước. Bài mở ở bảng bên phải, không che mất danh sách.</span>
      </div>
      <PanelState status={status} error={error} onRetry={onRetry} empty={sorted.length === 0} emptyText="Không có bài nào chờ duyệt.">
        <div className="md-table-scroll">
          <table className="md-queue">
            <thead>
              <tr>
                <th scope="col">Tư vấn viên</th>
                <th scope="col">Tình huống</th>
                <th scope="col">Hoàn thành</th>
                <th scope="col" className="md-right">Điểm AI</th>
                <th scope="col"><span className="md-sr">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item) => {
                const days = daysSince(item.completed_at);
                const name = advisorNames[item.advisor_id] || item.advisor_id;
                return (
                  <tr key={item.session_id}>
                    <td className="md-strong">{name}</td>
                    <td>{scenarioNames[item.scenario_id] || item.scenario_id}</td>
                    <td className={days != null && days >= 3 ? 'md-age md-age--old' : 'md-age'}>{dayLabel(days)}</td>
                    <td className="md-right md-strong">{item.ai_score == null ? '—' : `${fmtScore(item.ai_score)} / 3`}</td>
                    <td className="md-right">
                      <button type="button" className="md-btn md-btn--outline" aria-label={`Duyệt bài của ${name}`} onClick={() => onOpenReview(item.session_id)}>Duyệt</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </PanelState>
    </section>
  );
}

export function ManagerDashboard({
  queue, queueStatus, queueError, onRetryQueue, advisorNames, scenarioNames,
  onOpenReview, onNavigateTab, refreshToken = 0,
}) {
  const dash = useLoad(() => managerApi.getDashboard(WEEKS), `dashboard-${refreshToken}`, 'Không thể tải số liệu tổng quan.');
  const [drawerAdvisor, setDrawerAdvisor] = useState(null);
  const dashboard = dash.data;
  const rows = dashboard?.skill_matrix || [];
  const trend = dashboard?.team_trend || [];
  const totalAttempts = trend.reduce((sum, item) => sum + (item.attempts || 0), 0);
  const oldestId = [...queue].sort((a, b) => new Date(a.completed_at || 0) - new Date(b.completed_at || 0))[0]?.session_id;

  return (
    <div className="md-dashboard">
      <div className="md-title-row">
        <div>
          <h1>Tổng quan đội ngũ</h1>
          {dashboard && (
            <p>
              {dashboard.advisor_count} tư vấn viên, {totalAttempts} bài luyện trong {dashboard.weeks || WEEKS} tuần qua. Điểm kỹ năng chỉ tính các bài quản lý đã duyệt.
            </p>
          )}
        </div>
        {dashboard?.has_sample_data && (
          <p className="md-sample-note">Dữ liệu mẫu cho buổi demo, không phải số liệu sử dụng thật</p>
        )}
      </div>

      {dashboard && <TodayStrip dashboard={dashboard} oldestId={oldestId} onOpenReview={onOpenReview} onNavigateTab={onNavigateTab} />}

      <div className="md-row">
        <section className="md-panel md-panel--wide" aria-labelledby="md-map-h">
          <div className="md-panel-head">
            <h2 id="md-map-h" className="md-panel-title">Bản đồ kỹ năng</h2>
            <span className="md-panel-hint">Điểm trung bình theo rubric, thang 1 đến 3. Bấm một dòng để xem chi tiết.</span>
          </div>
          <PanelState status={dash.status} error={dash.error} onRetry={dash.reload} empty={rows.length === 0} emptyText="Chưa có tư vấn viên nào. Tạo tài khoản ở tab Tài khoản.">
            <SkillHeatmap rows={rows} onOpenAdvisor={setDrawerAdvisor} />
          </PanelState>
        </section>
        <Todos />
      </div>

      <div className="md-row">
        <section className="md-panel md-panel--wide" aria-labelledby="md-trend-h">
          <div className="md-panel-head">
            <h2 id="md-trend-h" className="md-panel-title">Điểm đội qua {dashboard?.weeks || WEEKS} tuần</h2>
            <span className="md-panel-hint">Đường nét đậm là điểm trung bình của cả đội; đường gạch là mức 2.</span>
          </div>
          <PanelState status={dash.status} error={dash.error} onRetry={dash.reload} empty={trend.every((item) => item.avg_score == null)} emptyText="Chưa có bài nào được duyệt trong khoảng thời gian này.">
            <TeamTrend trend={trend} />
          </PanelState>
        </section>
        <section className="md-panel" aria-labelledby="md-ai-h">
          <h2 id="md-ai-h" className="md-panel-title">AI chấm có đáng tin không?</h2>
          <PanelState status={dash.status} error={dash.error} onRetry={dash.reload} empty={!dashboard || (dashboard.ai_agreement || []).length === 0 || dashboard.approved_attempts === 0} emptyText="Chưa có bài nào được duyệt để so sánh điểm AI với điểm quản lý.">
            <AiAgreement items={dashboard?.ai_agreement || []} approved={dashboard?.approved_attempts ?? 0} />
          </PanelState>
        </section>
      </div>

      <ReviewQueue
        queue={queue}
        status={queueStatus}
        error={queueError}
        onRetry={onRetryQueue}
        advisorNames={advisorNames}
        scenarioNames={scenarioNames}
        onOpenReview={onOpenReview}
      />

      {drawerAdvisor && (
        <AdvisorDrawer
          row={drawerAdvisor}
          trend={dashboard?.advisor_trends?.[drawerAdvisor.advisor_id] || []}
          scenarioNames={scenarioNames}
          onClose={() => setDrawerAdvisor(null)}
          onOpenReview={onOpenReview}
        />
      )}
    </div>
  );
}
