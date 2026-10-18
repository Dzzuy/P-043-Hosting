import { useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { managerApi } from '../../api/managerApi';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { CRITERION_LABEL, fmtDayMonth, fmtScore } from '../../utils/scoreFormat';
import './reviewPanel.css';

const FINDING_STATUS = {
  supported: 'Đúng với nguồn',
  contradicted: 'Sai so với nguồn',
  unverifiable: 'Chưa kiểm chứng được',
};
const FINDING_SEVERITY = { warning: 'Mức cảnh báo', critical: 'Mức nghiêm trọng' };

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
    <article className="rp-card rp-voice">
      <h4>Sử dụng giọng nói của phiên này</h4>
      {status === 'loading' && <p role="status">Đang tải số liệu giọng nói…</p>}
      {status === 'error' && <p role="alert">{error} <button type="button" className="rp-link" onClick={retry}>Thử lại</button></p>}
      {status === 'ready' && usage && (
        usage.stt_requests + usage.tts_requests === 0
          ? <p>Phiên này chưa sử dụng giọng nói.</p>
          : <>
            <p>Nhận dạng: {usage.stt_requests} lượt, {usage.stt_billed_seconds.toFixed(1)} giây tính phí</p>
            <p>Phát giọng khách: {usage.tts_requests} lượt, {usage.tts_characters} ký tự</p>
            <p><strong>Chi phí ước tính: ${usage.estimated_usd.toFixed(6)}</strong></p>
            <small>Ước tính theo đơn giá cấu hình; hóa đơn nhà cung cấp có thể khác.</small>
          </>
      )}
    </article>
  );
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function ReviewContent({ detail, advisorName, scenarioTitle, position, hasNext, onClose, onApprove, onSkip }) {
  const draft = detail.ai_evaluation.result;
  const approvedReview = detail.manager_review;
  const canReview = Boolean(draft && !approvedReview && detail.attempt.evaluation_status === 'complete');
  const shown = approvedReview?.approved_result || draft;
  const messages = useMemo(() => detail.session.messages || [], [detail.session.messages]);
  const turnOf = useMemo(
    () => Object.fromEntries(messages.map((message, index) => [message.message_id, index + 1])),
    [messages],
  );
  const aiByCriterion = useMemo(
    () => Object.fromEntries((draft?.evaluations || []).map((item) => [item.criterion, item])),
    [draft],
  );
  const [scores, setScores] = useState(() => Object.fromEntries(
    (draft?.evaluations || []).filter((item) => item.status === 'assessed').map((item) => [item.criterion, item.score]),
  ));
  const [reasons, setReasons] = useState({});
  const [comment, setComment] = useState('');
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');

  const isChanged = (criterion) => canReview && aiByCriterion[criterion]?.status === 'assessed' && scores[criterion] !== aiByCriterion[criterion].score;
  const changedKeys = Object.keys(scores).filter(isChanged);

  const aiOverall = draft?.overall_score ?? null;
  let finalOverall;
  let changedCount;
  if (canReview) {
    finalOverall = mean(Object.values(scores));
    changedCount = changedKeys.length;
  } else {
    finalOverall = shown?.overall_score ?? null;
    changedCount = (shown?.evaluations || []).filter((item) => item.status === 'assessed' && aiByCriterion[item.criterion]?.score !== item.score).length;
  }

  const jumpToMessage = (messageId) => {
    const node = document.getElementById(`rp-msg-${messageId}`);
    if (!node) return;
    node.scrollIntoView({ block: 'center' });
    node.focus({ preventScroll: true });
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!canReview || status === 'saving') return;
    const missing = changedKeys.filter((key) => !(reasons[key] || '').trim());
    if (missing.length) {
      setError(`Nhập lý do sửa điểm cho: ${missing.map((key) => CRITERION_LABEL[key] || key).join(', ')}.`);
      document.getElementById(`rp-reason-${missing[0]}`)?.focus();
      return;
    }
    const overrides = Object.fromEntries(changedKeys.map((key) => [key, { score: scores[key], reason: reasons[key].trim() }]));
    const decision = { score_overrides: overrides };
    if (comment.trim()) decision.general_comment = comment.trim();
    setStatus('saving');
    setError('');
    try {
      await onApprove(decision);
    } catch (approvalError) {
      setStatus('idle');
      setError(approvalError.message || 'Không thể lưu đánh giá. Vui lòng thử lại.');
    }
  };

  const completed = fmtDayMonth(detail.attempt.completed_at);
  const aiLabel = aiOverall == null ? 'không có' : fmtScore(aiOverall);

  return (
    <>
      <header className="rp-head">
        <div className="rp-head-main">
          {canReview && position && <p className="rp-eyebrow">Bài {position.index} trong {position.total} chờ duyệt</p>}
          {approvedReview && <p className="rp-eyebrow">Đã duyệt{fmtDayMonth(approvedReview.reviewed_at) && ` ngày ${fmtDayMonth(approvedReview.reviewed_at)}`}</p>}
          <h2 id="rp-title">{advisorName}</h2>
          <p className="rp-scenario">{scenarioTitle}</p>
          <p className="rp-eyebrow">{completed && `Hoàn thành ${completed}, `}{messages.length} tin nhắn.</p>
        </div>
        <div
          className="rp-total"
          role="status"
          aria-label={`Điểm tổng sau duyệt ${fmtScore(finalOverall)} trên 3, AI chấm ${aiLabel}, đã đổi ${changedCount} điểm`}
        >
          <div className="rp-total-label">Điểm tổng sau duyệt</div>
          <div className="rp-total-value">
            {changedCount > 0 && aiOverall != null && <s>{fmtScore(aiOverall)}</s>}
            <strong>{fmtScore(finalOverall)}</strong>
            <span>/ 3</span>
          </div>
          <div className={changedCount > 0 ? 'rp-total-delta rp-total-delta--changed' : 'rp-total-delta'}>
            {changedCount > 0 ? `Đã đổi ${changedCount} điểm so với AI` : 'Chưa đổi điểm nào so với AI'}
          </div>
        </div>
        <button type="button" className="rp-close" aria-label="Đóng" onClick={onClose}><X size={18} aria-hidden="true" /></button>
      </header>

      <form className="rp-body" onSubmit={submit} noValidate>
        <section className="rp-transcript" aria-labelledby="rp-transcript-h">
          <h3 id="rp-transcript-h">Hội thoại</h3>
          {messages.length === 0 ? <p className="rp-empty">Phiên này chưa có hội thoại.</p> : (
            <ol>
              {messages.map((message, index) => (
                <li key={message.message_id} className={`rp-msg rp-msg--${message.role === 'advisor' ? 'advisor' : 'customer'}`}>
                  <span className="rp-msg-who">{message.role === 'advisor' ? 'Tư vấn viên' : 'Khách hàng'}, tin {index + 1}</span>
                  <div id={`rp-msg-${message.message_id}`} tabIndex={-1} className="rp-bubble">{message.content}</div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="rp-scores" aria-label="Điểm và bằng chứng">
          <div className="rp-scroll">
            <h3>Điểm và bằng chứng</h3>
            {!shown && <p className="rp-error" role="alert">Bài này chưa có bản chấm AI hợp lệ để quản lý duyệt.</p>}
            {(shown?.evaluations || []).map((evaluation) => {
              const ai = aiByCriterion[evaluation.criterion];
              const assessed = evaluation.status === 'assessed';
              const changed = isChanged(evaluation.criterion);
              const finalScore = canReview ? scores[evaluation.criterion] : evaluation.score;
              const label = CRITERION_LABEL[evaluation.criterion] || evaluation.criterion;
              const reasonId = `rp-reason-${evaluation.criterion}`;
              return (
                <article key={evaluation.criterion} className={changed ? 'rp-card rp-card--changed' : 'rp-card'}>
                  <div className="rp-card-head">
                    <h4>{label}</h4>
                    {assessed ? (
                      <>
                        <span className="rp-muted">AI chấm</span>
                        <strong>{ai?.score ?? evaluation.score}</strong>
                        {canReview ? (
                          <label className="rp-select">
                            <span>Điểm duyệt</span>
                            <select
                              value={finalScore}
                              onChange={(event) => setScores((current) => ({ ...current, [evaluation.criterion]: Number(event.target.value) }))}
                              disabled={status === 'saving'}
                            >
                              {[1, 2, 3].map((score) => <option key={score} value={score}>{score}</option>)}
                            </select>
                          </label>
                        ) : (
                          <span className="rp-final">
                            <span className="rp-muted">Điểm duyệt</span> <strong>{finalScore}</strong>
                          </span>
                        )}
                      </>
                    ) : <span className="rp-muted">Chưa chấm</span>}
                  </div>
                  {evaluation.evidence.map((item) => (
                    <button type="button" key={`${item.message_id}-${item.quote}`} className="rp-quote" onClick={() => jumpToMessage(item.message_id)}>
                      “{item.quote}”
                      {turnOf[item.message_id] && <span>Tin {turnOf[item.message_id]} trong hội thoại</span>}
                    </button>
                  ))}
                  <p className="rp-reason">{evaluation.reason}</p>
                  {!canReview && evaluation.manager_reason && (
                    <p className="rp-manager-reason"><strong>Lý do sửa điểm {ai?.score} → {evaluation.score}:</strong> {evaluation.manager_reason}</p>
                  )}
                  {changed && (
                    <div className="rp-change">
                      <label htmlFor={reasonId}>
                        Lý do sửa điểm {aiByCriterion[evaluation.criterion].score} → {finalScore} <span>(bắt buộc)</span>
                      </label>
                      <textarea
                        id={reasonId}
                        rows="2"
                        maxLength={2000}
                        required
                        value={reasons[evaluation.criterion] || ''}
                        onChange={(event) => setReasons((current) => ({ ...current, [evaluation.criterion]: event.target.value }))}
                        disabled={status === 'saving'}
                      />
                    </div>
                  )}
                </article>
              );
            })}

            {shown && (
              <article className="rp-card">
                <h4>Kiểm tra thông tin</h4>
                {(shown.factual_findings || []).length === 0
                  ? <p className="rp-reason">Không có phát biểu nào cần đối chiếu.</p>
                  : (
                    <ul className="rp-findings">
                      {shown.factual_findings.map((finding) => (
                        <li key={`${finding.message_id}-${finding.claim}`}>
                          <p className="rp-reason">
                            {turnOf[finding.message_id] ? `Tin ${turnOf[finding.message_id]}: ` : ''}“{finding.claim}”
                          </p>
                          <p className="rp-finding-meta">
                            {FINDING_STATUS[finding.status] || finding.status}
                            {FINDING_SEVERITY[finding.severity] ? `. ${FINDING_SEVERITY[finding.severity]}` : ''}. {finding.reason}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
              </article>
            )}

            <VoiceUsageCard sessionId={detail.attempt.session_id} />
          </div>

          <footer className="rp-foot">
            {canReview ? (
              <>
                <label htmlFor="rp-general">Nhận xét chung <span>(không bắt buộc, tư vấn viên sẽ thấy)</span></label>
                <textarea
                  id="rp-general"
                  rows="2"
                  maxLength={2000}
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  disabled={status === 'saving'}
                />
              </>
            ) : approvedReview?.general_comment ? (
              <>
                <strong className="rp-foot-label">Nhận xét chung</strong>
                <p className="rp-general-text">{approvedReview.general_comment}</p>
              </>
            ) : null}
            {error && <p className="rp-error" role="alert">{error}</p>}
            <div className="rp-actions">
              {!canReview && <button type="button" className="rp-btn rp-btn--outline" onClick={onClose}>Đóng</button>}
              {canReview && onSkip && hasNext && (
                <button type="button" className="rp-btn rp-btn--outline" onClick={onSkip} disabled={status === 'saving'}>Bỏ qua, bài sau</button>
              )}
              {canReview && (
                <button type="submit" className="rp-btn rp-btn--primary" disabled={status === 'saving'}>
                  {status === 'saving' ? 'Đang lưu…' : (hasNext ? 'Duyệt và mở bài tiếp theo' : 'Duyệt bài này')}
                </button>
              )}
            </div>
          </footer>
        </section>
      </form>
    </>
  );
}

export function ManagerReviewModal({ detail, onClose, ...rest }) {
  const { ref, onKeyDown } = useDialogFocus(onClose);
  const sessionId = detail.attempt.session_id;
  useEffect(() => {
    ref.current?.focus();
  }, [ref, sessionId]);
  return (
    <div className="rp-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside
        ref={ref}
        tabIndex={-1}
        className="rp-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rp-title"
        onKeyDown={onKeyDown}
      >
        <ReviewContent key={detail.attempt.session_id} detail={detail} onClose={onClose} {...rest} />
      </aside>
    </div>
  );
}
