import {
  RefreshIcon,
  BookIcon,
  ClockIcon,
  LightbulbIcon,
} from '../common/Icons';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';

export function EvaluationScorecard({
  result,
  scenario,
  onRetry,
  onBackToCatalog,
}) {
  if (!result || !result.result) {
    return (
      <div className="card-white" style={{ textAlign: 'center', padding: '60px 24px' }}>
        <div style={{ width: 44, height: 44, borderRadius: '50%', backgroundColor: '#F4F4F2', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
          <ClockIcon style={{ width: 22, height: 22, color: '#111111' }} />
        </div>
        <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#111111', marginBottom: 8 }}>
          Đang tổng hợp đánh giá từ Hệ thống Chấm điểm AI...
        </h3>
        <p style={{ fontSize: '0.88rem', color: '#737373', maxWidth: 460, margin: '0 auto 24px' }}>
          Hệ thống đang đối chiếu hội thoại với 5 tiêu chí Rubric chuẩn và kiểm chứng tính xác thực của thông số sản phẩm.
        </p>
        <Button variant="outline" onClick={onBackToCatalog}>
          Về danh sách tình huống
        </Button>
      </div>
    );
  }

  const evalData = result.result;
  const overallScore3 = evalData.overall_score;
  const approved = evalData.review_status === 'manager_approved';

  const criteriaLabels = {
    need_discovery: 'Need Discovery (Khai thác Nhu cầu)',
    product_knowledge: 'Product Knowledge (Kiến thức Sản phẩm)',
    objection_handling: 'Objection Handling (Xử lý Băn khoăn)',
    policy_accuracy: 'Policy Accuracy (Độ chính xác Chính sách)',
    closing_next_step: 'Closing / Next Step (Chốt & Bước tiếp theo)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1000, margin: '0 auto' }}>
      {/* HEADER CARD */}
      <div className="card-dark" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '4px 10px', borderRadius: 9999, marginBottom: 10 }}>
              <span style={{ fontSize: '0.72rem', color: '#E0E0E0', fontWeight: 600 }}>
                KẾT QUẢ ĐÁNH GIÁ THỰC CHIẾN • RUBRIC {evalData.rubric_version || '2.0'}
              </span>
            </div>
            <h1 style={{ fontSize: '1.6rem', fontWeight: 800, color: '#FFFFFF', lineHeight: 1.2 }}>
              {scenario?.title || 'Đánh giá phiên tư vấn khách hàng'}
            </h1>
            <p style={{ fontSize: '0.85rem', color: '#A3A3A3', marginTop: 4 }}>
              Phiên ID: <code style={{ color: '#E0E0E0' }}>{result.session_id}</code> • Trạng thái:{' '}
              <span style={{ color: '#FFFFFF', fontWeight: 600 }}>{approved ? 'Quản lý đã duyệt' : 'Bản nháp AI (Chờ Quản lý duyệt)'}</span>
              {' '}• Đã chấm {evalData.assessed_criteria_count}/5 kỹ năng
            </p>
          </div>

          <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: '2.4rem', fontWeight: 800, color: '#FFFFFF' }}>{overallScore3 ?? '—'}</span>
              <span style={{ fontSize: '1rem', color: '#888888' }}>/ 3</span>
            </div>
            <Badge variant="default" style={{ backgroundColor: '#555555', color: '#FFFFFF', border: 'none', padding: '6px 12px', fontSize: '0.82rem' }}>
              {approved ? 'KẾT QUẢ ĐÃ DUYỆT' : 'BẢN NHÁP AI • CHƯA DUYỆT'}
            </Badge>
          </div>
        </div>

        {evalData.closing_outcome_label && (
          <p style={{ fontSize: '0.9rem', color: '#FFFFFF' }}>
            Kết quả chốt: {evalData.closing_outcome_label}
          </p>
        )}

        {/* Strengths & Weaknesses Quick Summary */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginTop: 12, paddingTop: 16, borderTop: '1px solid rgba(255, 255, 255, 0.12)' }}>
          <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.05)', padding: '14px 16px', borderRadius: 10 }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#FFFFFF', display: 'block', marginBottom: 6 }}>
              + ĐIỂM MẠNH NỔI BẬT:
            </span>
            <ul style={{ listStyle: 'none', paddingLeft: 0, fontSize: '0.82rem', color: '#E0E0E0', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {(evalData.summary_strengths || []).map((s, idx) => (
                <li key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                  <span>•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.05)', padding: '14px 16px', borderRadius: 10 }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#E4E4E7', display: 'block', marginBottom: 6 }}>
              ! ĐIỂM CẦN RÈN LUYỆN:
            </span>
            <ul style={{ listStyle: 'none', paddingLeft: 0, fontSize: '0.82rem', color: '#E0E0E0', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {(evalData.summary_weaknesses || []).map((w, idx) => (
                <li key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                  <span>•</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* 5 RUBRIC CRITERIA DETAIL */}
      <div>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#111111', marginBottom: 14 }}>
          Chi tiết 5 Tiêu chí Rubric Đánh giá
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {(evalData.evaluations || []).map((crit, idx) => {
            const score = crit.score;
            return (
              <div
                key={idx}
                className="card-white"
                style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 28, height: 28, borderRadius: '50%', backgroundColor: '#111111', color: '#FFFFFF', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700 }}>
                      {idx + 1}
                    </div>
                    <div>
                      <h3 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#111111' }}>
                        {criteriaLabels[crit.criterion] || crit.criterion}
                      </h3>
                      <span style={{ fontSize: '0.75rem', color: '#737373' }}>
                        Trạng thái: {crit.status === 'assessed' ? 'Đã đánh giá qua hội thoại' : 'Chưa chấm — xem lý do'}
                      </span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#111111' }}>
                      {score ?? '—'} <span style={{ fontSize: '0.8rem', fontWeight: 500, color: '#737373' }}>/ 3</span>
                    </span>
                  </div>
                </div>

                {/* Reason & Feedback */}
                <p style={{ fontSize: '0.88rem', color: '#333333', lineHeight: 1.5, backgroundColor: '#FBFBFA', padding: '12px 16px', borderRadius: 8, border: '1px solid #F0F0EE' }}>
                  {crit.reason}
                </p>

                {/* Evidence quotes from conversation */}
                {crit.evidence && crit.evidence.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#737373' }}>
                      Trích dẫn bằng chứng từ hội thoại:
                    </span>
                    {crit.evidence.map((ev, eIdx) => (
                      <div
                        key={eIdx}
                        style={{
                          fontSize: '0.82rem',
                          fontStyle: 'italic',
                          color: '#404040',
                          backgroundColor: '#F5F5F3',
                          borderLeft: '3px solid #111111',
                          padding: '6px 12px',
                          borderRadius: '0 6px 6px 0',
                        }}
                      >
                        {ev.message_id ? <a href={`#message-${ev.message_id}`} style={{ color: 'inherit' }}>"{ev.quote}" ↗</a> : `"${ev.quote}"`}
                      </div>
                    ))}
                  </div>
                )}

                {crit.improvement_suggestion && (
                  <div style={{ fontSize: '0.82rem', color: '#111111', fontWeight: 500 }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><LightbulbIcon style={{ width: 13, height: 13 }} /> <strong>Gợi ý cải thiện:</strong></span> {crit.improvement_suggestion}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* FACTUAL FINDINGS (EVIDENCE BASED) */}
      {evalData.factual_findings && evalData.factual_findings.length > 0 && (
        <div className="card-white" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ borderBottom: '1px solid #F0F0EE', paddingBottom: 10 }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#111111', display: 'flex', alignItems: 'center', gap: 8 }}>
              <BookIcon style={{ width: 16, height: 16 }} />
              Đối chiếu thông tin thực tế với Kho Kiến thức VinFast
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {evalData.factual_findings.map((finding, fIdx) => (
              <div
                key={fIdx}
                style={{
                  padding: '12px 16px',
                  borderRadius: 8,
                  backgroundColor: '#F9F9F8',
                  border: '1px solid #EBEBE6',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: 12,
                }}
              >
                <div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#111111', marginBottom: 4 }}>
                    "{finding.claim}"
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#666666' }}>
                    {finding.reason}
                  </div>
                </div>
                <Badge variant={finding.status === 'supported' ? 'highlight' : 'default'}>
                  {finding.status === 'supported' ? 'Chính xác' : finding.status}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {evalData.recommended_next_practice && (
        <div className="card-white">
          <h3>Gợi ý luyện tập tiếp</h3>
          <p>{evalData.recommended_next_practice.reason}</p>
        </div>
      )}

      {/* ACTIONS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, flexWrap: 'wrap', gap: 12 }}>
        <Button variant="outline" onClick={onBackToCatalog}>
          ← Về danh sách kịch bản
        </Button>

        <Button variant="primary" onClick={onRetry} icon={<RefreshIcon style={{ width: 14, height: 14 }} />}>
          Luyện tập lại kịch bản này
        </Button>
      </div>
    </div>
  );
}
