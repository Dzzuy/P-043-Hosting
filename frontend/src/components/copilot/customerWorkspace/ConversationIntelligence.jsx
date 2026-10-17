import { Sparkles, RefreshCw, X, ArrowDownToLine, ChevronRight } from 'lucide-react';
import { IconButton } from './WorkspacePrimitives';
import { displayDateTime } from './workspaceData';
import { CustomerProfile } from './CustomerProfile';

function SourceLinks({ ids = [], onSourceClick }) {
  return <div className="sw-ci-sources">{ids.map((id, index) => <button key={id} type="button" className="sw-text-button sw-fact-source" onClick={() => onSourceClick?.(id)}>Tin nguồn {index + 1}<ChevronRight size={11} /></button>)}</div>;
}

function IntelligenceList({ title, items, onSourceClick }) {
  if (!items.length) return null;
  return <section className="sw-ci-section"><h3>{title}</h3><ul className="sw-ci-list">{items.map((item, index) => <li key={index}><p>{item.text}</p><SourceLinks ids={item.sourceMessageIds} onSourceClick={onSourceClick} /></li>)}</ul></section>;
}

export function ConversationSummary({ customer, onAnalyze, analyzing, onSourceClick, onHistory, onConfirmFact, changes }) {
  const { recap, keyPoints, outcomes, commitments } = customer.intelligence;
  return <section className="sw-summary-content" id="sw-conversation-summary" aria-label="Bối cảnh khách hàng">
    <p className="sw-intelligence-eyebrow">Customer Intelligence</p>
    <p className="sw-summary-updated">{customer.updatedAt ? `Đã phân tích đến ${displayDateTime(customer.updatedAt)}` : 'Chưa phân tích'}</p>
    {customer.pendingAnalysis > 0 && <p className="sw-freshness">{customer.updatedAt ? `Có ${customer.pendingAnalysis} tin nhắn mới chưa phân tích.` : 'Hội thoại chưa được phân tích.'}</p>}
    <section className="sw-ci-section sw-ci-recap"><h3>Recap — Tổng quan</h3><p>{recap || 'Chưa có tổng quan được lưu. Phân tích hội thoại để cập nhật.'}</p></section>
    {keyPoints.length > 0 && <section className="sw-ci-section"><h3>Key Points — Nội dung trao đổi</h3><ul className="sw-ci-list">{keyPoints.map((point, index) => <li key={index}>
      <div className="sw-ci-topic"><strong>{point.topic || point.question}</strong><span className={`sw-ci-status ${point.status === 'open' ? 'is-open' : ''}`}>{point.status === 'open' ? 'Còn bỏ ngỏ' : 'Đã giải đáp'}</span></div>
      {point.question && point.question !== point.topic && <p><span className="sw-ci-label">Khách:</span> {point.question}</p>}
      {point.answer && point.answer !== point.topic && <p><span className="sw-ci-label">Sales:</span> {point.answer}</p>}
      <SourceLinks ids={point.sourceMessageIds} onSourceClick={onSourceClick} />
    </li>)}</ul></section>}
    <IntelligenceList title="Outcomes — Kết quả tư vấn" items={outcomes} onSourceClick={onSourceClick} />
    <IntelligenceList title="Commitments — Cam kết" items={commitments} onSourceClick={onSourceClick} />
    <div className="sw-inline-actions sw-intelligence-actions"><button type="button" className="sw-secondary-button" disabled={analyzing || !customer.loaded || !customer.messageTotal} onClick={onAnalyze}><RefreshCw size={13} className={analyzing ? 'sw-spin' : ''} />{analyzing ? 'Đang phân tích…' : recap ? 'Cập nhật phân tích' : 'Phân tích hội thoại'}</button></div>
    <details className="sw-intelligence-section sw-ci-facts"><summary><h3>Kiểm tra / sửa dữ kiện</h3></summary><CustomerProfile customer={customer} onSourceClick={onSourceClick} onConfirmFact={onConfirmFact} /></details>
    {changes && <details className="sw-analysis-changes"><summary>Xem thay đổi sau phân tích</summary><ul>{changes.map((change, index) => <li key={index}>{change}</li>)}</ul></details>}
    <div className="sw-inline-actions"><button type="button" className="sw-text-button" onClick={onHistory}>Xem mốc chăm sóc<ChevronRight size={12} /></button></div>
  </section>;
}

export function DraftReply({ customer, enabled, onToggle, preferenceBusy, busy, onGenerate, onInsert, onDismiss, hasComposerText, dismissed }) {
  const hasDraft = Boolean(customer.draft && !dismissed);
  return <section className="sw-inline-draft" aria-label="Bản nháp trả lời AI">
    <div className="sw-inline-heading"><strong><Sparkles size={14} />Gợi ý trả lời AI</strong><div className="sw-draft-heading-actions"><button type="button" role="switch" className={`sw-switch ${enabled ? 'is-on' : ''}`} aria-checked={enabled} disabled={preferenceBusy || busy} aria-label="Bật gợi ý trả lời AI" onClick={onToggle}><span /></button><IconButton label="Đóng gợi ý trả lời" onClick={onDismiss}><X size={14} /></IconButton></div></div>
    {!enabled ? <div className="sw-draft-off"><p>Bật gợi ý để tạo bản nháp cho khách hàng này.</p><button type="button" className="sw-secondary-button" disabled={preferenceBusy} onClick={onToggle}>Bật gợi ý trả lời</button></div> : <>
      {hasDraft ? <>
        {customer.draftStale && <p className="sw-freshness" role="status">Bản nháp chưa bao gồm tin mới. Tạo lại trước khi sử dụng.</p>}
        <p className="sw-draft-text">{customer.draft}</p>
        <small className="sw-draft-context">Tạo lúc {displayDateTime(customer.draftGeneratedAt)}{!customer.draftContextKnown && ' · Bản nháp cũ, cần kiểm tra lại ngữ cảnh'}</small>
        {customer.draftContext && <details className="sw-draft-references"><summary>Ngữ cảnh và tham chiếu</summary><p>{customer.draftContext}</p>{customer.draftSources.length > 0 && <><small>Tham chiếu do AI nêu, cần đối chiếu khi tư vấn:</small><ul>{customer.draftSources.map((source, index) => <li key={index}>{source}</li>)}</ul></>}</details>}
      </> : <p className="sw-secondary">Chưa có bản nháp. AI chỉ tạo khi bạn yêu cầu.</p>}
      <div className="sw-inline-actions"><button type="button" className="sw-text-button" onClick={onDismiss}>Bỏ</button><div><button type="button" className="sw-secondary-button" disabled={busy || !customer.loaded} onClick={onGenerate}><RefreshCw size={13} className={busy ? 'sw-spin' : ''} />{busy ? 'Đang tạo…' : hasDraft ? 'Tạo lại' : 'Tạo gợi ý'}</button>{hasDraft && (hasComposerText ? <>{[['replace', 'Thay thế'], ['append', 'Chèn thêm'], ['copy', 'Sao chép']].map(([mode, label]) => <button key={mode} type="button" className="sw-secondary-button" disabled={busy || customer.draftStale} onClick={() => onInsert(mode)}>{label}</button>)}</> : <button type="button" className="sw-primary-button" disabled={busy || customer.draftStale} onClick={() => onInsert('replace')}><ArrowDownToLine size={13} />Dùng bản nháp</button>)}</div></div>
    </>}
  </section>;
}
