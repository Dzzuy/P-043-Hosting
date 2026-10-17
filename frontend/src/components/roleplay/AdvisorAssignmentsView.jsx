import { useCallback, useEffect, useState } from 'react';
import { practiceApi } from '../../api/practiceApi';
import { BookIcon, RefreshIcon } from '../common/Icons';

const STATUS = { assigned: 'Chưa bắt đầu', in_progress: 'Đang luyện', completed: 'Hoàn thành' };

export function AdvisorAssignmentsView({ scenarios, onStart, onOpenAttempt, reloadToken }) {
  const [assignments, setAssignments] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      setAssignments(await practiceApi.getAssignments());
      setStatus('ready');
    } catch (cause) {
      setError(cause.message || 'Không thể tải bài được giao.');
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    let active = true;
    practiceApi.getAssignments().then((items) => {
      if (!active) return;
      setAssignments(items);
      setStatus('ready');
    }).catch((cause) => {
      if (!active) return;
      setError(cause.message || 'Không thể tải bài được giao.');
      setStatus('error');
    });
    return () => { active = false; };
  }, [reloadToken]);

  const scenarioNames = Object.fromEntries(scenarios.map((item) => [item.scenario_id, item.title]));

  return (
    <section className="practice-assignments">
      <div className="practice-assignments-header">
        <span className="practice-assignment-icon"><BookIcon aria-hidden="true" /></span>
        <div>
          <h2>Bài tập được giao</h2>
          <p>
            Hoàn thành các bài tập do Quản lý giao để cập nhật tiến độ và năng lực cá nhân.
          </p>
        </div>
        <button type="button" className="practice-refresh" onClick={load} disabled={status === 'loading'}>
          <RefreshIcon aria-hidden="true" /> Làm mới
        </button>
      </div>

      {status === 'loading' && <p role="status" style={{ color: 'var(--muted)', padding: '12px 0' }}>Đang tải bài được giao…</p>}
      {error && (
        <p role="alert" style={{ color: '#dc2626', marginBottom: 14 }}>
          {error} <button type="button" className="btn-outline" style={{ marginLeft: 8 }} onClick={load}>Thử lại</button>
        </p>
      )}

      {status === 'ready' && assignments.length === 0 && (
        <div className="practice-assignments-empty">
          <BookIcon aria-hidden="true" />
          <p>Hiện tại bạn chưa có bài tập nào được giao.<br />Hãy tự do chọn các tình huống bên dưới để tự luyện tập!</p>
        </div>
      )}

      {status === 'ready' && assignments.length > 0 && (
        <div style={{ display: 'grid', gap: 12, marginTop: 14 }}>
          {assignments.map((assignment) => (
            <article
              key={assignment.assignment_id}
              className="manager-assignment-card-item"
            >
              <div>
                <strong style={{ fontSize: '0.98rem', color: 'var(--primary)' }}>{assignment.title}</strong>
                <p style={{ margin: '4px 0 6px', color: 'var(--secondary)', fontSize: '0.88rem' }}>
                  Kịch bản: <strong>{scenarioNames[assignment.scenario_id] || assignment.scenario_id}</strong>
                </p>
                <small style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>
                  Trạng thái: <strong>{STATUS[assignment.status] || assignment.status}</strong> · Hạn: {assignment.due_date || 'Không đặt'}
                </small>
              </div>

              <div>
                {assignment.status === 'completed' && assignment.session_id ? (
                  <button
                    type="button"
                    className="btn-outline"
                    onClick={() => onOpenAttempt(assignment.session_id)}
                    style={{ padding: '8px 16px', fontSize: '0.85rem' }}
                  >
                    Xem kết quả
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => onStart(assignment)}
                    disabled={!scenarioNames[assignment.scenario_id]}
                    style={{ padding: '8px 18px', fontSize: '0.85rem' }}
                  >
                    {assignment.status === 'in_progress' ? 'Luyện tiếp bài này →' : 'Bắt đầu bài được giao →'}
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
