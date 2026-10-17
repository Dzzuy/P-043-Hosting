import { useEffect, useMemo, useState } from 'react';
import { managerApi } from '../../api/managerApi';

const CRITERION_LABELS = {
  need_discovery: 'Khám phá nhu cầu',
  product_knowledge: 'Kiến thức sản phẩm',
  objection_handling: 'Xử lý phản đối',
  policy_accuracy: 'Độ chính xác chính sách',
  closing_next_step: 'Chốt bước tiếp theo',
};

function ScoreEditor({ evaluation, value, onChange, readOnly = false }) {
  const assessed = evaluation.status === 'assessed';
  return (
    <article className="review-criterion">
      <div className="review-criterion-heading">
        <div>
          <strong>{CRITERION_LABELS[evaluation.criterion] || evaluation.criterion}</strong>
          <span>{assessed ? 'Đã đánh giá' : 'Chưa chấm — xem lý do'}</span>
        </div>
        {assessed && readOnly && <strong>{value}/3</strong>}
        {assessed && !readOnly && (
          <label>
            <span className="sr-only">Điểm quản lý</span>
            <select value={value} onChange={(event) => onChange(Number(event.target.value))}>
              {[1, 2, 3].map((score) => <option key={score} value={score}>{score}/3</option>)}
            </select>
          </label>
        )}
      </div>
      <p>{evaluation.reason}</p>
      {evaluation.improvement_suggestion && <p className="review-improvement">↗ {evaluation.improvement_suggestion}</p>}
      {evaluation.evidence.length > 0 && (
        <div className="review-evidence-list">
          {evaluation.evidence.map((evidence) => (
            <blockquote key={`${evaluation.criterion}-${evidence.message_id}`}>
              “{evidence.quote}” <cite>{evidence.message_id}</cite>
            </blockquote>
          ))}
        </div>
      )}
    </article>
  );
}

function VoiceUsageCard({ sessionId }) {
  const [usage, setUsage] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    managerApi.getVoiceUsage(sessionId)
      .then((result) => {
        if (!active) return;
        setUsage(result);
        setStatus('ready');
      })
      .catch((loadError) => {
        if (!active) return;
        setError(loadError.message || 'Không thể tải chi phí giọng nói.');
        setStatus('error');
      });
    return () => { active = false; };
  }, [sessionId]);

  const retry = async () => {
    setStatus('loading');
    setError('');
    try {
      setUsage(await managerApi.getVoiceUsage(sessionId));
      setStatus('ready');
    } catch (loadError) {
      setError(loadError.message || 'Không thể tải chi phí giọng nói.');
      setStatus('error');
    }
  };

  return (
    <section className="manager-voice-usage">
      <h3>Sử dụng giọng nói · phiên này</h3>
      {status === 'loading' && <p role="status">Đang tải số liệu giọng nói…</p>}
      {status === 'error' && <p role="alert">{error} <button type="button" onClick={retry}>Thử lại</button></p>}
      {status === 'ready' && usage && (
        usage.stt_requests + usage.tts_requests === 0
          ? <p>Phiên này chưa sử dụng giọng nói.</p>
          : <>
            <p>Nhận dạng: {usage.stt_requests} lượt · {usage.stt_billed_seconds.toFixed(1)} giây tính phí</p>
            <p>Phát giọng khách: {usage.tts_requests} lượt · {usage.tts_characters} ký tự</p>
            <strong>Chi phí ước tính: ${usage.estimated_usd.toFixed(6)}</strong>
            <small>Ước tính theo đơn giá cấu hình; hóa đơn nhà cung cấp có thể khác.</small>
          </>
      )}
    </section>
  );
}

export function ManagerReviewModal({ detail, onClose, onApprove }) {
  const draft = detail.ai_evaluation.result;
  const approvedReview = detail.manager_review;
  const canReview = Boolean(draft && !approvedReview && detail.attempt.evaluation_status === 'complete');
  const shownResult = approvedReview?.approved_result || draft;
  const [scores, setScores] = useState(() => Object.fromEntries(
    (shownResult?.evaluations || [])
      .filter((item) => item.status === 'assessed')
      .map((item) => [item.criterion, item.score]),
  ));
  const [reason, setReason] = useState('');
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');
  const messagesById = useMemo(
    () => Object.fromEntries(detail.session.messages.map((message) => [message.message_id, message])),
    [detail.session.messages],
  );

  const submit = async (event) => {
    event.preventDefault();
    if (!canReview) return;
    if (!reason.trim()) {
      setError('Vui lòng ghi lý do xác nhận hoặc điều chỉnh đánh giá.');
      return;
    }
    const overrides = Object.fromEntries(
      (draft?.evaluations || [])
        .filter((item) => item.status === 'assessed' && scores[item.criterion] !== item.score)
        .map((item) => [item.criterion, scores[item.criterion]]),
    );
    setStatus('saving');
    setError('');
    try {
      await onApprove({ score_overrides: overrides, change_reason: reason.trim() });
    } catch (approvalError) {
      setStatus('idle');
      setError(approvalError.message || 'Không thể lưu đánh giá. Vui lòng thử lại.');
    }
  };

  return (
    <div className="review-modal-backdrop" role="presentation">
      <section className="review-modal" role="dialog" aria-modal="true" aria-labelledby="review-dialog-title">
        <header className="review-modal-header">
          <div>
            <span>◇ Human-in-the-Loop Review</span>
            <h2 id="review-dialog-title">{approvedReview ? 'Kết quả đã duyệt' : 'Thẩm định kết quả AI'}</h2>
            <p>Advisor: {detail.attempt.advisor_id} · Scenario: {detail.attempt.scenario_id}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Đóng cửa sổ đánh giá">×</button>
        </header>

        <form onSubmit={submit} className="review-modal-body">
          <div className="review-detail-column">
            <section className="review-summary-card">
              <div>
                <span>{approvedReview ? 'Điểm đã duyệt' : 'AI draft score'}</span>
                <strong>{shownResult?.overall_score?.toFixed(1) ?? '—'}<small>/3</small></strong>
              </div>
              <div>
                <span>Rubric version</span>
                <strong className="review-version">{shownResult?.rubric_version || '—'}</strong>
              </div>
            </section>

            <VoiceUsageCard sessionId={detail.attempt.session_id} />

            {approvedReview && (
              <section className="manager-approved-note">
                <strong>Quản lý {approvedReview.manager_id} đã duyệt</strong>
                <p>Lý do: {approvedReview.change_reason}</p>
                <small>Điểm AI ban đầu: {draft?.overall_score?.toFixed(1) ?? '—'}/3</small>
              </section>
            )}

            <section>
              <h3>Transcript</h3>
              <div className="review-transcript">
                {detail.session.messages.length === 0 && <p>Phiên này chưa có transcript.</p>}
                {detail.session.messages.map((message) => (
                  <div key={message.message_id} className={`review-message ${message.role}`}>
                    <span>{message.role === 'advisor' ? 'Tư vấn viên' : 'AI Customer'}</span>
                    <p>{message.content}</p>
                    <small>{message.message_id}</small>
                  </div>
                ))}
              </div>
            </section>

            {shownResult?.factual_findings?.length > 0 && (
              <section>
                <h3>Đối chiếu thông tin thực tế</h3>
                <div className="review-findings">
                  {shownResult.factual_findings.map((finding) => (
                    <article key={`${finding.message_id}-${finding.claim}`}>
                      <strong>{finding.status}</strong>
                      <p>“{finding.claim}”</p>
                      <span>{finding.reason}</span>
                      {messagesById[finding.message_id] && <small>Nguồn transcript: {finding.message_id}</small>}
                    </article>
                  ))}
                </div>
              </section>
            )}
          </div>

          <div className="review-score-column">
            <div className="review-section-heading">
              <div>
                <h3>Điểm theo rubric</h3>
                <p>Chỉ tiêu chí đã có evidence mới được điều chỉnh.</p>
              </div>
              <span>{Object.values(scores).length} tiêu chí</span>
            </div>
            <div className="review-criteria-list">
              {shownResult?.evaluations.map((evaluation) => (
                <ScoreEditor
                  key={evaluation.criterion}
                  evaluation={evaluation}
                  value={scores[evaluation.criterion] ?? evaluation.score ?? ''}
                  onChange={(score) => setScores((current) => ({ ...current, [evaluation.criterion]: score }))}
                  readOnly={Boolean(approvedReview)}
                />
              ))}
            </div>

            {!canReview && !approvedReview && <p className="manager-queue-error">Attempt này chưa có AI draft hợp lệ để manager duyệt.</p>}
            {canReview && <label className="review-reason-field">
              <span>Lý do xác nhận/điều chỉnh <strong>*</strong></span>
              <textarea
                rows="4"
                maxLength="2000"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Ví dụ: Điểm phù hợp với transcript và evidence; xác nhận AI draft."
                disabled={status === 'saving' || status === 'saved'}
              />
            </label>}
            {error && <div className="review-error" role="alert">{error}</div>}

            <footer className="review-modal-actions">
              <button type="button" className="review-secondary" onClick={onClose}>Hủy</button>
              {canReview && <button type="submit" className="review-approve" disabled={status !== 'idle'}>
                {status === 'saving' ? 'Đang lưu…' : 'Phê duyệt & lưu'}
              </button>}
            </footer>
          </div>
        </form>
      </section>
    </div>
  );
}
