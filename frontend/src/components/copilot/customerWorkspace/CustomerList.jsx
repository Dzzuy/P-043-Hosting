import { Search, SlidersHorizontal, ChevronDown, Users, Inbox, AlertCircle, Sparkles } from 'lucide-react';
import { Avatar, StageBadge, IconButton } from './WorkspacePrimitives';
import { filterCustomers } from './workspaceData';

export function CustomerList({ customers, selectedId, onSelect, query, onQueryChange, filter, onFilterChange, status, error, onRetry, onOpenCopilot }) {
  const filtered = filterCustomers(customers, query, filter);
  const tabs = [
    { id: 'all', title: 'Tất cả', count: customers.length },
    { id: 'caring', title: 'Đang chăm sóc', count: customers.filter((customer) => !['new', 'won', 'lost'].includes(customer.stageId)).length },
    { id: 'attention', title: 'Cần chú ý', count: customers.filter((customer) => customer.attention).length },
  ];
  return <section className="sw-customer-list" aria-label="Danh sách khách hàng">
    <div className="sw-list-heading"><h2>Khách hàng <span>({customers.length})</span></h2><Users size={18} /></div>
    {onOpenCopilot && <button type="button" className="sw-secondary-button sw-list-copilot" onClick={onOpenCopilot}><Sparkles size={15} />Hỏi Copilot</button>}
    <div className="sw-list-search-row"><label className="sw-search sw-list-search"><Search size={17} /><input aria-label="Tìm kiếm khách hàng" placeholder="Tìm kiếm khách hàng..." value={query} onChange={(event) => onQueryChange(event.target.value)} /></label><IconButton label={filter === 'attention' ? 'Bỏ lọc khách cần chú ý' : 'Lọc khách cần chú ý'} className={filter === 'attention' ? 'is-active' : ''} onClick={() => onFilterChange(filter === 'attention' ? 'all' : 'attention')}><SlidersHorizontal size={17} /></IconButton></div>
    <div className="sw-customer-filters" aria-label="Lọc trạng thái khách hàng">{tabs.map((tab) => <button key={tab.id} type="button" aria-pressed={filter === tab.id} className={filter === tab.id ? 'is-active' : ''} onClick={() => onFilterChange(tab.id)}>{tab.title}<span>{tab.count}</span></button>)}</div>
    <div className="sw-list-sort"><span>{filtered.length} khách hàng</span><span>Tin nhắn gần nhất <ChevronDown size={12} /></span></div>
    {filter === 'attention' && <p className="sw-attention-explanation">Khách chờ phản hồi hoặc có công việc quan trọng cần cập nhật trạng thái.</p>}
    <div className="sw-customer-rows">
      {status === 'loading' && !customers.length ? <div className="sw-loading-state" role="status" aria-label="Đang tải khách hàng">{[1, 2, 3, 4].map((id) => <div className="sw-skeleton" key={id} />)}</div> : error ? <div className="sw-empty" role="alert"><Inbox size={28} /><strong>Chưa tải được khách hàng</strong><p>{error}</p><button type="button" className="sw-text-button" onClick={onRetry}>Thử lại</button></div> : filtered.length === 0 ? <div className="sw-empty"><Inbox size={28} /><strong>{customers.length ? 'Không tìm thấy khách hàng' : 'Chưa có khách hàng'}</strong><p>{customers.length ? 'Thử tên hoặc dòng xe khác.' : 'Khách hàng trong hệ thống sẽ hiển thị tại đây.'}</p>{customers.length > 0 && <button type="button" className="sw-text-button" onClick={() => { onQueryChange(''); onFilterChange('all'); }}>Xóa bộ lọc</button>}</div> : filtered.map((customer) => {
        const latest = customer.messages.at(-1);
        return <button key={customer.id} type="button" className={`sw-customer-row ${selectedId === customer.id ? 'is-selected' : ''}`} onClick={() => onSelect(customer.id)} aria-pressed={selectedId === customer.id}>
          <Avatar customer={customer} />
          <div className="sw-customer-row-content">
            <div className="sw-customer-row-name"><strong>{customer.name}</strong><time>{latest?.time || customer.lastMessageTime}</time></div>
            <p className="sw-message-preview">{latest?.role === 'sales' ? 'Bạn: ' : ''}{latest?.content || customer.preview}</p>
            <p className="sw-customer-vehicle">{customer.model.replace('Hyundai ', '')} <span>·</span> {customer.budget}</p>
            <div className="sw-row-status"><StageBadge customer={customer} />{customer.attention && <span className="sw-attention-indicator" title={customer.attentionReason} aria-label={customer.attentionReason}><AlertCircle size={13} /></span>}</div>
          </div>
        </button>;
      })}
    </div>
    <div className="sw-list-footer"><span className="sw-channel-dot" />Khách hàng và hội thoại từ hệ thống</div>
  </section>;
}
