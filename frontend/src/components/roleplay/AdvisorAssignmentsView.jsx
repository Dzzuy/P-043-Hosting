import { RefreshCw } from 'lucide-react';
import { fmtDayMonth } from '../../utils/scoreFormat';
import './advisorProgress.css';

const STATUS = { assigned: 'Chưa bắt đầu', in_progress: 'Đang luyện', completed: 'Hoàn thành' };

function dueInfo(assignment) {
  if (!assignment.due_date) return { text: 'Không đặt hạn', warn: false };
  const due = new Date(`${assignment.due_date}T00:00:00`);
  const today = new Date();
  const days = Math.round((due - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
  const base = `Hạn ${fmtDayMonth(due)}`;
  if (assignment.status === 'completed') return { text: base, warn: false };
  if (days < 0) return { text: `${base}, quá hạn ${-days} ngày`, warn: true };
  if (days === 0) return { text: `${base}, hết hạn hôm nay`, warn: true };
  if (days <= 3) return { text: `${base}, còn ${days} ngày`, warn: true };
  return { text: base, warn: false };
}

export function AdvisorAssignmentsView({ scenarios, assignments, status, error, onReload, onStart }) {
  const scenarioNames = Object.fromEntries(scenarios.map((item) => [item.scenario_id, item.title]));
  const open = assignments.filter((item) => item.status !== 'completed');

  return (
    <section className="ap-card" aria-labelledby="ap-assign-h">
      <div className="ap-card-head">
        <h2 id="ap-assign-h">Bài được giao</h2>
        <button type="button" className="ap-text-btn ap-refresh" onClick={onReload} disabled={status === 'loading'}>
          <RefreshCw size={14} aria-hidden="true" /> Làm mới
        </button>
      </div>

      {status === 'loading' && <p className="ap-state" role="status">Đang tải bài được giao…</p>}
      {status === 'error' && (
        <p className="ap-state ap-state--error" role="alert">
          {error || 'Không thể tải bài được giao.'} <button type="button" className="ap-link" onClick={onReload}>Thử lại</button>
        </p>
      )}
      {status === 'ready' && open.length === 0 && (
        <p className="ap-state">Hiện bạn chưa có bài nào được giao. Cứ chọn một tình huống trong thư viện để tự luyện.</p>
      )}
      {status === 'ready' && open.length > 0 && (
        <ul className="ap-list">
          {open.map((assignment) => {
            const due = dueInfo(assignment);
            const title = scenarioNames[assignment.scenario_id];
            return (
              <li className="ap-assignment" key={assignment.assignment_id}>
                <span className="ap-assignment-main">
                  <span className="ap-assignment-title">{assignment.title}</span>
                  {title && title !== assignment.title && <span className="ap-assignment-meta">{title}</span>}
                  <span className={due.warn ? 'ap-assignment-meta ap-assignment-meta--warn' : 'ap-assignment-meta'}>
                    {STATUS[assignment.status] || assignment.status}. {due.text}
                  </span>
                </span>
                <button
                  type="button"
                  className="ap-btn ap-btn--primary"
                  onClick={() => onStart(assignment)}
                  disabled={!title}
                >
                  {assignment.status === 'in_progress' ? 'Luyện tiếp' : 'Bắt đầu'}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
