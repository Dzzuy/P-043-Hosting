import { useState } from 'react';
import { BookIcon, CheckIcon, ChevronLeft, ClockIcon, LightbulbIcon, RefreshIcon, TargetIcon } from '../common/Icons';
import './roleplayScorecard.css';
import './advisorProgress.css';

import { CRITERION_LABEL as labels } from '../../utils/scoreFormat';

function isAssessed(criterion) {
  return criterion.status === 'assessed' && [1, 2, 3].includes(criterion.score);
}

const scoreBands = { 3: 'Tốt', 2: 'Đạt', 1: 'Cần rèn' };

function downloadReport(result, scenario, evaluation) {
  const lines = [
    'KẾT QUẢ ĐÁNH GIÁ LUYỆN TẬP',
    scenario?.title || 'Đánh giá phiên tư vấn khách hàng',
    `Phiên ID: ${result.session_id}`,
    `Rubric: ${evaluation.rubric_version || 'không rõ'}`,
    `Trạng thái: ${evaluation.review_status === 'manager_approved' ? 'Quản lý đã duyệt' : 'Bản nháp AI, chờ Quản lý duyệt'}`,
    `Tổng điểm: ${evaluation.overall_score ?? 'Chưa chấm'} / 3 · Đã chấm ${evaluation.assessed_criteria_count}/5 kỹ năng`,
    '', 'ĐIỂM MẠNH',
    ...(evaluation.summary_strengths?.length ? evaluation.summary_strengths : ['Chưa có dữ liệu nổi bật.']),
    '', 'ĐIỂM CẦN RÈN LUYỆN',
    ...(evaluation.summary_weaknesses?.length ? evaluation.summary_weaknesses : ['Chưa có nhận xét.']),
    '', 'CHI TIẾT RUBRIC',
  ];
  for (const criterion of evaluation.evaluations || []) {
    lines.push('', `${labels[criterion.criterion] || criterion.criterion}: ${criterion.score ?? 'Chưa chấm'} / 3`,
      criterion.reason || '',
      ...(criterion.evidence || []).map((item) => `Trích dẫn: "${item.quote}"`),
      criterion.improvement_suggestion ? `Gợi ý: ${criterion.improvement_suggestion}` : '');
  }
  const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `danh-gia-${result.session_id || 'practice'}.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function EvaluationScorecard({ result, scenario, onRetry, onBackToCatalog, onOpenAttempt, showTranscriptLinks = false, generalComment = null }) {
  const [collapsed, setCollapsed] = useState({});
  if (!result?.result) {
    return (
      <div className="evaluation-pending" role="status">
        <ClockIcon aria-hidden="true" />
        <h2>Đang tổng hợp đánh giá từ Hệ thống Chấm điểm AI...</h2>
        <p>Hệ thống đang đối chiếu hội thoại với 5 tiêu chí Rubric chuẩn và kiểm chứng thông số sản phẩm.</p>
        <button type="button" onClick={onBackToCatalog}>Về danh sách tình huống</button>
      </div>
    );
  }

  const evaluation = result.result;
  const approved = evaluation.review_status === 'manager_approved';
  const score = typeof evaluation.overall_score === 'number' ? evaluation.overall_score : null;
  const scoreText = score === null ? '—' : score.toLocaleString('vi-VN', { maximumFractionDigits: 1 });
  const progress = score === null ? 0 : Math.min(100, Math.max(0, score / 3 * 100));
  const highlight = (evaluation.evaluations || []).reduce((lowest, criterion, index) => {
    if (!isAssessed(criterion) || !criterion.improvement_suggestion?.trim()) return lowest;
    return !lowest || criterion.score < lowest.criterion.score ? { criterion, index } : lowest;
  }, null);
  const summary = [...(evaluation.summary_strengths || []), ...(evaluation.summary_weaknesses || [])].join(' ');

  return (
    <div className="evaluation-page">
      <header className="evaluation-header">
        <div className="evaluation-toolbar">
          <button type="button" className="evaluation-back" onClick={onBackToCatalog}><ChevronLeft aria-hidden="true" /> Quay lại danh sách</button>
          <button type="button" className="evaluation-download" onClick={() => downloadReport(result, scenario, evaluation)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4" /></svg>
            Tải báo cáo
          </button>
        </div>
        <span className="evaluation-eyebrow">KẾT QUẢ ĐÁNH GIÁ LUYỆN TẬP • RUBRIC {evaluation.rubric_version || 'chưa rõ'}</span>
        <h1>{scenario?.title || 'Đánh giá phiên tư vấn khách hàng'}</h1>
        <p>Phiên ID: {result.session_id} <span aria-hidden="true">•</span> Trạng thái: <strong>{approved ? 'Quản lý đã duyệt' : 'Bản nháp AI (Chờ Quản lý duyệt)'}</strong> <span aria-hidden="true">•</span> Đã chấm {evaluation.assessed_criteria_count}/5 kỹ năng</p>
      </header>

      {highlight && <section className="evaluation-highlight" aria-labelledby="evaluation-highlight-heading">
        <h2 id="evaluation-highlight-heading">Gợi ý cải thiện: {labels[highlight.criterion.criterion] || highlight.criterion.criterion}</h2>
        <p>{highlight.criterion.improvement_suggestion}</p>
        <a href={`#evaluation-criterion-row-${highlight.index}`} onClick={() => setCollapsed((current) => ({ ...current, [highlight.index]: false }))}>Xem bằng chứng trong hội thoại</a>
      </section>}

      <section className="evaluation-overview" aria-label="Tổng quan đánh giá">
        <div className="evaluation-score-side">
          <div className="evaluation-score-ring" style={{ '--score-progress': `${progress}%` }} aria-label={`Tổng điểm ${scoreText} trên 3`}>
            <div><strong>{scoreText}</strong><span>/ 3</span><small>Tổng điểm</small></div>
          </div>
          <span className={`evaluation-status ${approved ? 'approved' : ''}`}>{approved ? <CheckIcon aria-hidden="true" /> : <ClockIcon aria-hidden="true" />}{approved ? 'KẾT QUẢ ĐÃ DUYỆT' : 'Chờ quản lý duyệt. Điểm chỉ tính vào tiến độ sau khi duyệt.'}</span>
        </div>
        <div className="evaluation-overview-body">
          <h2>Tổng quan đánh giá</h2>
          <p>{summary || 'Chưa có nhận xét tổng quan. Xem chi tiết từng tiêu chí bên dưới.'}</p>
          {evaluation.closing_outcome_label && <p className="evaluation-closing-outcome">Kết quả chốt: <strong>{evaluation.closing_outcome_label}</strong></p>}
          <div className="evaluation-summary-grid">
            <div className="evaluation-summary-card strengths">
              <h3><span><CheckIcon aria-hidden="true" /></span>Điểm mạnh nổi bật</h3>
              {evaluation.summary_strengths?.length
                ? <ul>{evaluation.summary_strengths.map((item, index) => <li key={index}>{item}</li>)}</ul>
                : <p>Chưa có dữ liệu nổi bật.</p>}
            </div>
            <div className="evaluation-summary-card weaknesses">
              <h3><span aria-hidden="true">▥</span>Điểm cần rèn luyện</h3>
              {evaluation.summary_weaknesses?.length
                ? <ul>{evaluation.summary_weaknesses.map((item, index) => <li key={index}>{item}</li>)}</ul>
                : <p>Chưa có nhận xét.</p>}
            </div>
          </div>
        </div>
      </section>

      <div className="evaluation-section-heading"><h2>Chi tiết 5 Tiêu chí Rubric Đánh giá</h2><span><ClockIcon aria-hidden="true" /> Đã chấm {evaluation.assessed_criteria_count}/5 kỹ năng</span></div>
      <div className="evaluation-criteria">
        {(evaluation.evaluations || []).map((criterion, index) => {
          const isOpen = collapsed[index] !== true;
          const panelId = `evaluation-criterion-${index}`;
          return (
            <section id={`evaluation-criterion-row-${index}`} className="evaluation-criterion" key={criterion.criterion || index}>
              <button type="button" className="evaluation-criterion-toggle" aria-expanded={isOpen} aria-controls={panelId} onClick={() => setCollapsed((current) => ({ ...current, [index]: !current[index] }))}>
                <span className="evaluation-criterion-number">{index + 1}</span>
                <span className="evaluation-criterion-name">{labels[criterion.criterion] || criterion.criterion}</span>
                <span className={`evaluation-criterion-score ${isAssessed(criterion) ? `band-${criterion.score}` : 'unassessed'}`}>{isAssessed(criterion) ? <><strong>{criterion.score} / 3</strong> {scoreBands[criterion.score]}</> : 'Chưa đủ dữ liệu'}</span>
                <span className={`evaluation-chevron ${isOpen ? 'open' : ''}`} aria-hidden="true">⌄</span>
              </button>
              {isOpen && <div id={panelId} className="evaluation-criterion-detail">
                <div className="evaluation-reason"><TargetIcon aria-hidden="true" /><div><h3>Mô tả tiêu chí</h3><p>{criterion.reason || (criterion.status === 'assessed' ? 'Chưa có nhận xét.' : 'Chưa chấm tiêu chí này từ hội thoại.')}</p></div></div>
                {criterion.evidence?.length > 0 && <div className="evaluation-evidence">
                  <h3><span aria-hidden="true">“</span> Trích dẫn bằng chứng từ hội thoại</h3>
                  {criterion.evidence.map((item, evidenceIndex) => <div className="evaluation-quote" key={evidenceIndex}>
                    {item.message_id && showTranscriptLinks
                      ? <a href={`#message-${item.message_id}`}>"{item.quote}" <span aria-hidden="true">↗</span></a>
                      : item.message_id && onOpenAttempt
                        ? <button type="button" onClick={() => onOpenAttempt(result.session_id)} title="Mở hội thoại đã lưu">"{item.quote}" <span aria-hidden="true">↗</span></button>
                        : <span>"{item.quote}"</span>}
                  </div>)}
                </div>}
                {criterion.manager_reason && <p className="ap-manager-reason"><strong>Lý do quản lý sửa điểm:</strong> {criterion.manager_reason}</p>}
                {criterion.improvement_suggestion && <div className="evaluation-improvement"><LightbulbIcon aria-hidden="true" /><div><h3>Gợi ý cải thiện</h3><p>{criterion.improvement_suggestion}</p></div></div>}
              </div>}
            </section>
          );
        })}
      </div>

      {evaluation.factual_findings?.length > 0 && <section className="evaluation-extra">
        <h2><BookIcon aria-hidden="true" /> Đối chiếu thông tin với Kho Kiến thức VinFast</h2>
        {evaluation.factual_findings.map((finding, index) => <div className="evaluation-finding" key={index}><div><strong>"{finding.claim}"</strong><p>{finding.reason}</p></div><span>{finding.status === 'supported' ? 'Chính xác' : finding.status}</span></div>)}
      </section>}
      {evaluation.recommended_next_practice && <section className="evaluation-extra"><h2>Gợi ý luyện tập tiếp</h2><p>{evaluation.recommended_next_practice.reason}</p></section>}
      {generalComment && <div className="ap-manager-note"><h3>Nhận xét chung của quản lý</h3><p>{generalComment}</p></div>}
      <div className="evaluation-actions">
        <button type="button" onClick={onBackToCatalog}>Về danh sách kịch bản</button>
        <button type="button" onClick={onRetry}><RefreshIcon aria-hidden="true" /> Luyện tập lại kịch bản này</button>
      </div>
    </div>
  );
}
