import { Sparkles, RefreshCw, X, ArrowDownToLine, ChevronRight } from 'lucide-react';
import { IconButton } from './WorkspacePrimitives';
import { displayDateTime } from './workspaceData';
import { CustomerProfile } from './CustomerProfile';
import { CustomerHistory } from './CustomerHistory';

function cleanSalesAnswer(text = '') {
  const stripped = text.trim().replace(/^sales\s+(?:cho biết|báo|nói|tư vấn|trả lời|xác nhận|thông tin|chia sẻ)(?:\s+rằng|\s+là)?\s*:?\s*/i, '');
  return stripped ? stripped.charAt(0).toUpperCase() + stripped.slice(1) : text;
}

function SourceLinks({ ids = [], onSourceClick }) {
  if (!ids.length) return null;
  return <span className="sw-ci-sources">{ids.map((id, index) => <button key={id} type="button" className="sw-text-button sw-fact-source" onClick={() => onSourceClick?.(id)}>Nguồn {index + 1}</button>)}</span>;
}

export function ConversationSummary({ customer, onAnalyze, analyzing, onSourceClick, onHistory, onConfirmFact, changes }) {
  const { recap, keyPoints } = customer.intelligence;
  const sortedPoints = [...keyPoints].sort((a, b) => (a.status === 'open' ? -1 : 1) - (b.status === 'open' ? -1 : 1));
  const statusLabels = { open: 'Còn bỏ ngỏ', answered: 'Đã trả lời', confirmed: 'Đã xác nhận', irrelevant: 'Không còn liên quan' };
  return <section className="sw-summary-content" id="sw-conversation-summary" aria-label="Bối cảnh khách hàng">
    <div className="sw-ci-topbar">
      <div className="sw-ci-topbar-meta">
        <span className="sw-summary-updated">{customer.updatedAt ? `Đã phân tích ${displayDateTime(customer.updatedAt)}` : 'Chưa phân tích AI'}</span>
        {customer.pendingAnalysis > 0 && <span className="sw-unprocessed-pill">{customer.updatedAt ? `+${customer.pendingAnalysis} tin mới` : `${customer.pendingAnalysis} tin chưa phân tích`}</span>}
      </div>
      <button type="button" className="sw-secondary-button sw-ci-refresh-btn" disabled={analyzing || !customer.loaded || !customer.messageTotal} onClick={onAnalyze}>
        <RefreshCw size={12} className={analyzing ? 'sw-spin' : ''} />
        <span>{analyzing ? 'Đang phân tích…' : recap ? 'Cập nhật phân tích' : 'Phân tích hội thoại'}</span>
      </button>
    </div>
    {changes && <details className="sw-analysis-changes"><summary>Xem thay đổi sau phân tích</summary><ul>{changes.map((change, index) => <li key={index}>{change}</li>)}</ul></details>}

    <section className="sw-ci-section sw-ci-quick-profile">
      <h3>Hồ sơ nhanh</h3>
      <div className="sw-quick-profile-grid">
        <div className="sw-quick-profile-cell"><span>Xe quan tâm</span><strong>{customer.model}</strong></div>
        <div className="sw-quick-profile-cell"><span>Thanh toán</span><strong>{customer.payment}</strong></div>
        <div className="sw-quick-profile-cell"><span>Ngân sách</span><strong>{customer.budget}</strong></div>
        <div className="sw-quick-profile-cell"><span>Thời điểm mua</span><strong>{customer.profile?.purchase_timeline || 'Chưa xác định'}</strong></div>
      </div>
      <details className="sw-intelligence-section sw-ci-facts">
        <summary>Sửa / Xác nhận dữ kiện chi tiết</summary>
        <CustomerProfile customer={customer} onSourceClick={onSourceClick} onConfirmFact={onConfirmFact} />
      </details>
    </section>

    <section className="sw-ci-section sw-ci-recap">
      <h3>Tổng quan tình hình</h3>
      <p>{recap || 'Chưa có tổng quan được lưu. Bấm Phân tích hội thoại để AI tổng hợp.'}</p>
    </section>

    {sortedPoints.length > 0 && (
      <section className="sw-ci-section">
        <h3>Nội dung đã trao đổi <span>({sortedPoints.length})</span></h3>
        <ul className="sw-ci-list">
          {sortedPoints.map((point, index) => (
            <li key={index} className={point.status === 'open' ? 'is-open-point' : ''}>
              <div className="sw-ci-topic">
                <strong>{point.topic || point.question}</strong>
                <span className={`sw-ci-status ${point.status === 'open' ? 'is-open' : ''}`}>{statusLabels[point.status] || point.status}</span>
              </div>
              {point.question && point.question !== point.topic && <p className="sw-ci-qa"><span className="sw-ci-label">Khách:</span> {point.question}</p>}
              {point.answer && point.answer !== point.topic && <p className="sw-ci-qa"><span className="sw-ci-label">Sales:</span> {cleanSalesAnswer(point.answer)}</p>}
              <SourceLinks ids={point.sourceMessageIds} onSourceClick={onSourceClick} />
            </li>
          ))}
        </ul>
      </section>
    )}

    <CustomerHistory key={customer.customerId} customer={customer} onSourceClick={onSourceClick} onHistory={onHistory} />
  </section>;
}

export function DraftReply({ customer, busy, onGenerate, onInsert, onDismiss, hasComposerText, dismissed }) {
  const hasDraft = Boolean(customer.draft && !dismissed);
  return <section className="sw-inline-draft" aria-label="Bản nháp trả lời AI">
    <div className="sw-inline-heading">
      <strong><Sparkles size={14} />Gợi ý trả lời tin nhắn</strong>
      <div className="sw-draft-heading-actions">
        <IconButton label="Đóng gợi ý trả lời" onClick={onDismiss}><X size={14} /></IconButton>
      </div>
    </div>
    {busy && !hasDraft ? (
      <p className="sw-secondary" role="status"><RefreshCw size={13} className="sw-spin" style={{ verticalAlign: 'middle', marginRight: 6 }} />AI đang đọc lịch sử hội thoại và tài liệu VinFast để soạn câu trả lời…</p>
    ) : hasDraft ? (
      <>
        {customer.draftStale && <p className="sw-freshness" role="status">Bản nháp chưa bao gồm tin nhắn mới nhất. Bấm <strong>Tạo lại</strong> để cập nhật.</p>}
        <p className="sw-draft-text">{customer.draft}</p>
        <small className="sw-draft-context">Tạo lúc {displayDateTime(customer.draftGeneratedAt)}{!customer.draftContextKnown && ' · Bản nháp cũ, cần kiểm tra lại ngữ cảnh'}</small>
        {customer.draftContext && (
          <details className="sw-draft-references">
            <summary>Ngữ cảnh & tài liệu tham khảo</summary>
            <p><strong>Tin nhắn khách:</strong> “{customer.draftContext}”</p>
            {customer.draftSources.length > 0 && (
              <>
                <small>Tài liệu đối chiếu:</small>
                <ul>{customer.draftSources.map((source, index) => <li key={index}>{source}</li>)}</ul>
              </>
            )}
          </details>
        )}
      </>
    ) : (
      <p className="sw-secondary">Bấm <strong>Tạo gợi ý</strong> để AI đọc lịch sử chat và soạn câu trả lời cho tin nhắn mới nhất của khách.</p>
    )}
    <div className="sw-inline-actions">
      <button type="button" className="sw-text-button" onClick={onDismiss}>Đóng</button>
      <div>
        <button type="button" className="sw-secondary-button" disabled={busy || !customer.loaded} onClick={onGenerate}>
          <RefreshCw size={13} className={busy ? 'sw-spin' : ''} />
          {busy ? 'Đang tạo…' : hasDraft ? 'Tạo lại' : 'Tạo gợi ý'}
        </button>
        {hasDraft && (
          hasComposerText ? (
            <>{[['replace', 'Thay thế'], ['append', 'Chèn thêm'], ['copy', 'Sao chép']].map(([mode, label]) => (
              <button key={mode} type="button" className="sw-secondary-button" disabled={busy || customer.draftStale} onClick={() => onInsert(mode)}>{label}</button>
            ))}</>
          ) : (
            <button type="button" className="sw-primary-button" disabled={busy || customer.draftStale} onClick={() => onInsert('replace')}>
              <ArrowDownToLine size={13} />Dùng bản nháp
            </button>
          )
        )}
      </div>
    </div>
  </section>;
}
