import { useCallback, useEffect, useState } from 'react';
import { managerApi } from '../../api/managerApi';
import { AlertCircleIcon, TrophyIcon } from '../common/Icons';

const SKILLS = {
  need_discovery: 'Khám phá nhu cầu',
  product_knowledge: 'Kiến thức sản phẩm',
  objection_handling: 'Xử lý phản đối',
  policy_accuracy: 'Độ chính xác chính sách',
  closing_next_step: 'Chốt bước tiếp theo',
};

export function TeamPerformanceView({ onNavigateTab }) {
  const [advisors, setAdvisors] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      setAdvisors(await managerApi.getAdvisors());
      setStatus('ready');
    } catch (cause) {
      setError(cause.message || 'Không thể tải năng lực đội ngũ.');
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    let active = true;
    managerApi.getAdvisors().then((items) => {
      if (!active) return;
      setAdvisors(items);
      setStatus('ready');
    }).catch((cause) => {
      if (!active) return;
      setError(cause.message || 'Không thể tải năng lực đội ngũ.');
      setStatus('error');
    });
    return () => { active = false; };
  }, []);

  return (
    <section className="card-white" style={{ padding: 28 }}>
      <div className="manager-assignment-header">
        <div>
          <h2>Năng lực & Bảng xếp hạng Đội ngũ</h2>
          <p>Điểm trung bình được tính từ các phiên thực chiến đã được Manager phê duyệt (cần tối thiểu 3 phiên để xếp hạng).</p>
        </div>
        <button type="button" className="btn-outline" onClick={load} disabled={status === 'loading'}>
          Làm mới
        </button>
      </div>

      {status === 'loading' && <p role="status" style={{ color: 'var(--muted)', padding: '16px 0' }}>Đang tính điểm từ các phiên đã duyệt…</p>}
      {status === 'error' && (
        <p role="alert" style={{ color: '#dc2626', marginBottom: 16 }}>
          {error} <button type="button" className="btn-outline" style={{ marginLeft: 8 }} onClick={load}>Thử lại</button>
        </p>
      )}

      {status === 'ready' && advisors.length === 0 && (
        <div className="manager-banner-warning">
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><AlertCircleIcon style={{ width: 14, height: 14 }} /> Hiện chưa có tài khoản Advisor nào trong hệ thống.</span>
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

      {status === 'ready' && advisors.length > 0 && (
        <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
          {advisors.map((advisor) => (
            <article
              key={advisor.advisor_id}
              className="card-white"
              style={{ padding: 22, border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, #18181B, #3F3F46)',
                      color: '#FFF',
                      display: 'grid',
                      placeItems: 'center',
                      fontWeight: 700,
                      fontSize: '1.1rem',
                    }}
                  >
                    {advisor.display_name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary)' }}>
                      {advisor.display_name}
                    </h3>
                    <small style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>
                      {advisor.completed_sessions} phiên hoàn thành · {advisor.approved_sessions} phiên đã duyệt
                    </small>
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--primary)' }}>
                    {advisor.average_score == null ? 'Chưa có điểm' : `${advisor.average_score.toFixed(2)} / 3.0`}
                  </div>
                  <small style={{ color: 'var(--muted)', fontSize: '0.8rem', fontWeight: 600 }}>
                    {advisor.rank == null
                      ? `Chưa đủ điều kiện xếp hạng (${advisor.scored_sessions}/3 phiên)`
                      : <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><TrophyIcon style={{ width: 12, height: 12 }} /> Xếp hạng: #{advisor.rank}</span>}
                  </small>
                </div>
              </div>

              {advisor.skill_summaries.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 16, paddingTop: 14, borderTop: '1px solid #F0F0EE' }}>
                  {advisor.skill_summaries.map((skill) => (
                    <span
                      key={skill.criterion}
                      style={{
                        padding: '4px 10px',
                        borderRadius: 'var(--radius-pill)',
                        backgroundColor: 'var(--surface-alt)',
                        border: '1px solid var(--border)',
                        fontSize: '0.78rem',
                        color: 'var(--secondary)',
                      }}
                    >
                      {SKILLS[skill.criterion] || skill.criterion}: <strong style={{ color: 'var(--primary)' }}>{skill.average_score.toFixed(1)}/3</strong> <small>({skill.assessed_count} lượt)</small>
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
