import { useCallback, useEffect, useState } from 'react';
import { managerApi } from '../../api/managerApi';
import { practiceApi } from '../../api/practiceApi';
import { AlertCircleIcon } from '../common/Icons';

const STATUS = { assigned: 'Đã giao', in_progress: 'Đang luyện', completed: 'Hoàn thành' };

function todayLocalDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

export function ManagerAssignmentsView({ onNavigateTab }) {
  const [assignments, setAssignments] = useState([]);
  const [advisors, setAdvisors] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: '', advisor_id: '', scenario_id: '', due_date: '' });

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const [assignmentList, advisorList, scenarioList] = await Promise.all([
        managerApi.getAssignments(), managerApi.getAdvisors(), practiceApi.getScenarios(),
      ]);
      setAssignments(assignmentList);
      setAdvisors(advisorList);
      setScenarios(scenarioList);
      setStatus('ready');
    } catch (cause) {
      setError(cause.message || 'Không thể tải bài được giao.');
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([managerApi.getAssignments(), managerApi.getAdvisors(), practiceApi.getScenarios()])
      .then(([assignmentList, advisorList, scenarioList]) => {
        if (!active) return;
        setAssignments(assignmentList);
        setAdvisors(advisorList);
        setScenarios(scenarioList);
        setStatus('ready');
      }).catch((cause) => {
        if (!active) return;
        setError(cause.message || 'Không thể tải bài được giao.');
        setStatus('error');
      });
    return () => { active = false; };
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const created = await managerApi.createAssignment({
        title: form.title.trim(), advisor_id: form.advisor_id,
        scenario_id: form.scenario_id, due_date: form.due_date || null,
      });
      setAssignments((current) => [created, ...current]);
      setForm({ title: '', advisor_id: '', scenario_id: '', due_date: '' });
    } catch (cause) {
      setError(cause.message || 'Không thể giao bài. Vui lòng thử lại.');
    } finally {
      setSaving(false);
    }
  };

  const advisorNames = Object.fromEntries(advisors.map((item) => [item.advisor_id, item.display_name]));
  const scenarioNames = Object.fromEntries(scenarios.map((item) => [item.scenario_id, item.title]));

  return (
    <section className="card-white" style={{ padding: 28 }}>
      <div className="manager-assignment-header">
        <div>
          <h2>Giao bài luyện tập</h2>
          <p>Mỗi bài gắn với một Advisor và một kịch bản Practice thật.</p>
        </div>
        <button type="button" className="btn-outline" onClick={load} disabled={status === 'loading'}>
          Làm mới
        </button>
      </div>

      {status === 'loading' && <p role="status">Đang tải bài luyện tập…</p>}
      {error && (
        <p role="alert" style={{ color: '#dc2626', marginBottom: 16 }}>
          {error} {status === 'error' && <button type="button" className="btn-outline" style={{ marginLeft: 8 }} onClick={load}>Thử lại</button>}
        </p>
      )}

      {status === 'ready' && (
        <>
          {advisors.length === 0 && (
            <div className="manager-banner-warning">
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><AlertCircleIcon style={{ width: 14, height: 14 }} /> Chưa có tài khoản Advisor hoạt động để giao bài.</span>
              {onNavigateTab && (
                <button
                  type="button"
                  className="manager-banner-warning-action"
                  onClick={() => onNavigateTab('accounts')}
                >
                  Chuyển sang tab "Tài khoản" để tạo ngay →
                </button>
              )}
            </div>
          )}

          <form onSubmit={submit} className="manager-assignment-form-card">
            <div className="manager-assignment-grid">
              <div className="form-group">
                <label className="form-label">Tiêu đề bài tập</label>
                <input
                  className="form-input"
                  required
                  maxLength={200}
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                  placeholder="Ví dụ: Tư vấn VF 5 cho khách chạy dịch vụ"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Tư vấn viên</label>
                <select
                  className="form-select"
                  required
                  value={form.advisor_id}
                  onChange={(event) => setForm({ ...form, advisor_id: event.target.value })}
                  disabled={advisors.length === 0}
                >
                  <option value="">{advisors.length === 0 ? 'Chưa có Advisor' : 'Chọn tư vấn viên'}</option>
                  {advisors.map((item) => (
                    <option key={item.advisor_id} value={item.advisor_id}>
                      {item.display_name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Kịch bản</label>
                <select
                  className="form-select"
                  required
                  value={form.scenario_id}
                  onChange={(event) => setForm({ ...form, scenario_id: event.target.value })}
                >
                  <option value="">Chọn kịch bản</option>
                  {scenarios.map((item) => (
                    <option key={item.scenario_id} value={item.scenario_id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Hạn hoàn thành</label>
                <input
                  type="date"
                  className="form-input"
                  min={todayLocalDate()}
                  value={form.due_date}
                  onChange={(event) => setForm({ ...form, due_date: event.target.value })}
                />
              </div>

              <button
                type="submit"
                className="btn-primary manager-assignment-submit-btn"
                disabled={saving || advisors.length === 0 || scenarios.length === 0}
              >
                {saving ? 'Đang giao…' : 'Giao bài'}
              </button>
            </div>
          </form>

          <h3 className="manager-assignment-list-title">
            Danh sách bài đã giao ({assignments.length})
          </h3>

          {assignments.length === 0 ? (
            <div className="card-white" style={{ padding: 32, textAlign: 'center', color: 'var(--muted)', border: '1px dashed var(--border)' }}>
              Chưa có bài nào được giao. Chọn Advisor và kịch bản ở trên để giao bài đầu tiên.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 12 }}>
              {assignments.map((item) => (
                <article key={item.assignment_id} className="manager-assignment-card-item">
                  <div>
                    <strong style={{ fontSize: '1rem', color: 'var(--primary)' }}>{item.title}</strong>
                    <p style={{ margin: '4px 0 6px', color: 'var(--secondary)', fontSize: '0.88rem' }}>
                      {advisorNames[item.advisor_id] || item.advisor_id} · {scenarioNames[item.scenario_id] || item.scenario_id}
                    </p>
                    <small style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>
                      Hạn: {item.due_date || 'Không đặt'}
                      {item.session_id && ` · Phiên: ${item.session_id}`}
                    </small>
                  </div>
                  <div>
                    <span className={`status-badge-${item.status}`}>
                      {STATUS[item.status] || item.status}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
