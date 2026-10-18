import { useState } from 'react';
import { Search, SlidersHorizontal, ChevronDown, Users, Inbox, AlertCircle, Sparkles, Check, RefreshCw } from 'lucide-react';
import { Avatar, StageBadge, IconButton } from './WorkspacePrimitives';
import { filterCustomers } from './workspaceData';

export function CustomerList({ customers, selectedId, onSelect, query, onQueryChange, filter, onFilterChange, status, error, onRetry, analysisIds = {}, batchProgress = null, onAnalyzeBatch, onCancelBatch }) {
  const [selecting, setSelecting] = useState(false);
  const [checked, setChecked] = useState({});
  const filtered = filterCustomers(customers, query, filter);
  const unprocessed = customers.filter((customer) => customer.pendingAnalysis > 0 && customer.messageTotal > 0);
  const selectedIds = customers.filter((customer) => checked[customer.id]).map((customer) => customer.id);
  const allUnprocessedSelected = unprocessed.length > 0 && unprocessed.every((customer) => checked[customer.id]);
  const tabs = [
    { id: 'all', title: 'Tất cả', count: customers.length },
    { id: 'caring', title: 'Đang chăm sóc', count: customers.filter((customer) => !['new', 'won', 'lost', 'needs_confirmation'].includes(customer.stageId)).length },
    { id: 'attention', title: 'Cần chú ý', count: customers.filter((customer) => customer.attention).length },
  ];

  function toggleRow(id) {
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function toggleSelectAllUnprocessed() {
    if (allUnprocessedSelected) {
      setChecked({});
    } else {
      setChecked(Object.fromEntries(unprocessed.map((customer) => [customer.id, true])));
    }
  }

  function startBatch(ids) {
    if (!ids.length) return;
    setSelecting(false);
    setChecked({});
    onAnalyzeBatch?.(ids);
  }

  return <section className="sw-customer-list" aria-label="Danh sách khách hàng">
    <div className="sw-list-heading">
      <h2>Khách hàng <span>({customers.length})</span></h2>
      {!batchProgress?.running && customers.length > 0 && (
        selecting ? (
          <button type="button" className="sw-text-button sw-select-cancel" onClick={() => { setSelecting(false); setChecked({}); }}>Hủy chọn</button>
        ) : (
          <button type="button" className={`sw-batch-trigger ${unprocessed.length > 0 ? 'has-pending' : ''}`} onClick={() => { setSelecting(true); setChecked({}); }} title="Chọn một vài hoặc tất cả hội thoại để AI phân tích">
            <Sparkles size={13} />
            <span>{unprocessed.length > 0 ? `Phân tích (${unprocessed.length})` : 'Phân tích AI'}</span>
          </button>
        )
      )}
      {!customers.length && <Users size={18} />}
    </div>
    {batchProgress?.running && (
      <div className="sw-batch-progress" role="status" aria-live="polite">
        <div className="sw-batch-progress-top">
          <span><RefreshCw size={12} className="sw-spin" /> Đang phân tích {batchProgress.completed}/{batchProgress.total}{batchProgress.currentLabel ? ` · ${batchProgress.currentLabel}` : '…'}</span>
          <button type="button" className="sw-text-button sw-batch-stop" onClick={onCancelBatch}>Dừng</button>
        </div>
        <div className="sw-batch-progress-track">
          <span style={{ width: `${Math.max(6, Math.round((batchProgress.completed / Math.max(1, batchProgress.total)) * 100))}%` }} />
        </div>
      </div>
    )}
    {selecting && !batchProgress?.running && (
      <div className="sw-selection-bar" role="region" aria-label="Tùy chọn phân tích hàng loạt">
        <div className="sw-selection-bar-top">
          {unprocessed.length > 0 ? (
            <button type="button" className="sw-select-all-btn" onClick={toggleSelectAllUnprocessed}>
              <span className={`sw-row-checkbox ${allUnprocessedSelected ? 'is-checked' : ''}`}>{allUnprocessedSelected && <Check size={11} />}</span>
              <span>Chọn tất cả có tin mới ({unprocessed.length})</span>
            </button>
          ) : (
            <span className="sw-selection-hint">Tích chọn hội thoại muốn phân tích lại</span>
          )}
          {selectedIds.length > 0 && <button type="button" className="sw-text-button" onClick={() => setChecked({})}>Bỏ chọn ({selectedIds.length})</button>}
        </div>
        <button
          type="button"
          className="sw-primary-button sw-selection-run-btn"
          disabled={selectedIds.length === 0 && unprocessed.length === 0}
          onClick={() => startBatch(selectedIds.length > 0 ? selectedIds : unprocessed.map((c) => c.id))}
        >
          <Sparkles size={13} />
          <span>
            {selectedIds.length > 0
              ? `Phân tích ${selectedIds.length} cuộc đã chọn`
              : `Phân tích tất cả có tin mới (${unprocessed.length})`}
          </span>
        </button>
      </div>
    )}
    <div className="sw-list-search-row"><label className="sw-search sw-list-search"><Search size={17} /><input aria-label="Tìm kiếm khách hàng" placeholder="Tìm kiếm khách hàng..." value={query} onChange={(event) => onQueryChange(event.target.value)} /></label><IconButton label={filter === 'attention' ? 'Bỏ lọc khách cần chú ý' : 'Lọc khách cần chú ý'} className={filter === 'attention' ? 'is-active' : ''} onClick={() => onFilterChange(filter === 'attention' ? 'all' : 'attention')}><SlidersHorizontal size={17} /></IconButton></div>
    <div className="sw-customer-filters" aria-label="Lọc trạng thái khách hàng">{tabs.map((tab) => <button key={tab.id} type="button" aria-pressed={filter === tab.id} className={filter === tab.id ? 'is-active' : ''} onClick={() => onFilterChange(tab.id)}>{tab.title}<span>{tab.count}</span></button>)}</div>
    <div className="sw-list-sort"><span>{filtered.length} khách hàng</span><span>Tin nhắn gần nhất <ChevronDown size={12} /></span></div>
    {filter === 'attention' && <p className="sw-attention-explanation">Khách chờ phản hồi hoặc có công việc quan trọng cần cập nhật trạng thái.</p>}
    <div className="sw-customer-rows">
      {status === 'loading' && !customers.length ? <div className="sw-loading-state" role="status" aria-label="Đang tải khách hàng">{[1, 2, 3, 4].map((id) => <div className="sw-skeleton" key={id} />)}</div> : error ? <div className="sw-empty" role="alert"><Inbox size={28} /><strong>Chưa tải được khách hàng</strong><p>{error}</p><button type="button" className="sw-text-button" onClick={onRetry}>Thử lại</button></div> : filtered.length === 0 ? <div className="sw-empty"><Inbox size={28} /><strong>{customers.length ? 'Không tìm thấy khách hàng' : 'Chưa có khách hàng'}</strong><p>{customers.length ? 'Thử tên hoặc dòng xe khác.' : 'Khách hàng trong hệ thống sẽ hiển thị tại đây.'}</p>{customers.length > 0 && <button type="button" className="sw-text-button" onClick={() => { onQueryChange(''); onFilterChange('all'); }}>Xóa bộ lọc</button>}</div> : filtered.map((customer) => {
        const latest = customer.messages.at(-1);
        const isAnalyzing = Boolean(analysisIds[customer.id]);
        const isChecked = Boolean(checked[customer.id]);
        return <button key={customer.id} type="button" className={`sw-customer-row ${!selecting && selectedId === customer.id ? 'is-selected' : ''} ${selecting && isChecked ? 'is-checked-row' : ''}`} onClick={() => selecting ? toggleRow(customer.id) : onSelect(customer.id)} aria-pressed={selecting ? isChecked : selectedId === customer.id}>
          {selecting && <span className={`sw-row-checkbox ${isChecked ? 'is-checked' : ''}`} aria-hidden="true">{isChecked && <Check size={11} />}</span>}
          <Avatar customer={customer} />
          <div className="sw-customer-row-content">
            <div className="sw-customer-row-name"><strong>{customer.name}</strong><time>{latest?.time || customer.lastMessageTime}</time></div>
            <p className="sw-message-preview">{latest?.role === 'sales' ? 'Bạn: ' : ''}{latest?.content || customer.preview}</p>
            <div className="sw-row-status">
              {isAnalyzing ? (
                <span className="sw-analyzing-pill"><RefreshCw size={11} className="sw-spin" /> Đang phân tích AI…</span>
              ) : customer.analysisVersion === 0 && customer.pendingAnalysis > 0 ? (
                <span className="sw-unprocessed-pill">Chưa phân tích · {customer.pendingAnalysis} tin</span>
              ) : (
                <>
                  <StageBadge customer={customer} />
                  {customer.pendingAnalysis > 0 && <span className="sw-unprocessed-pill">+{customer.pendingAnalysis} tin mới</span>}
                </>
              )}
              {customer.attention && <span className="sw-attention-indicator" title={customer.attentionReason} aria-label={customer.attentionReason}><AlertCircle size={13} /></span>}
            </div>
          </div>
        </button>;
      })}
    </div>
  </section>;
}
