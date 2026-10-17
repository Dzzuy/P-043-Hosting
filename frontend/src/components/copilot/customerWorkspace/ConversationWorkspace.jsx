import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ChevronRight, Star, Plus, MessageSquare, Smile, Send, Sparkles, CheckCheck, ListTodo, RefreshCw, ChevronDown, X } from 'lucide-react';
import { Avatar, StageBadge, IconButton, CopilotBubble } from './WorkspacePrimitives';
import { DraftReply } from './ConversationIntelligence';
import { LeadStageEditor } from './CustomerToolsDrawer';
import { headerFacts, taskCounts } from './workspaceData';
import { useWorkspaceClock } from './useCustomerWorkspace';
import { replySuggestionsAvailable } from './workspaceFeatures';

function ConversationViewer({ customer, highlight, onLoadOlder, loadingOlder }) {
  const scrollRef = useRef(null);
  const messageRefs = useRef(new Map());
  const lastMessageId = customer.messages.at(-1)?.id;
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [lastMessageId]);
  useEffect(() => {
    const target = highlight?.messageId && messageRefs.current.get(highlight.messageId);
    if (target) { target.scrollIntoView({ behavior: 'smooth', block: 'center' }); target.focus({ preventScroll: true }); }
  }, [highlight]);
  async function load(beforeSeq) {
    const stream = scrollRef.current;
    const height = stream.scrollHeight; const top = stream.scrollTop;
    await onLoadOlder(beforeSeq);
    requestAnimationFrame(() => { if (stream.isConnected) stream.scrollTop = top + stream.scrollHeight - height; });
  }
  return <div ref={scrollRef} className="sw-message-stream" aria-label="Lịch sử tin nhắn">
    {customer.nextBeforeSeq && <button type="button" className="sw-secondary-button sw-load-older" disabled={loadingOlder} onClick={() => load(customer.nextBeforeSeq)}>{loadingOlder ? 'Đang tải…' : 'Tải tin nhắn cũ hơn'}</button>}
    {!customer.messages.length && <div className="sw-empty"><MessageSquare size={25} /><strong>Chưa có tin nhắn</strong><p>Tin nhắn được lưu trong hội thoại sẽ hiển thị tại đây.</p></div>}
    {customer.messages.map((message, index) => {
      const isSales = message.role === 'sales';
      return <div key={message.id}>
        {index > 0 && message.seq > customer.messages[index - 1].seq + 1 && <button type="button" className="sw-text-button sw-load-older" disabled={loadingOlder} onClick={() => load(message.seq)}>Tải phần hội thoại còn thiếu</button>}
        {(index === 0 || customer.messages[index - 1].date !== message.date) && <div className="sw-date-separator"><span>{message.date ? new Date(`${message.date}T12:00:00`).toLocaleDateString('vi-VN') : 'Chưa rõ ngày'}</span></div>}
        <article ref={(node) => { if (node) messageRefs.current.set(message.id, node); else messageRefs.current.delete(message.id); }} tabIndex={-1} className={`sw-chat-message ${isSales ? 'is-sales' : 'is-customer'} ${highlight?.messageId === message.id ? 'is-highlighted' : ''}`} aria-label={`Tin nhắn ${isSales ? 'Sales' : customer.name} lúc ${message.time}`}>
          <Avatar customer={customer} sales={isSales} size="small" /><div className="sw-message-body"><div className="sw-message-meta"><strong>{isSales ? 'Sales' : message.role === 'system' ? 'Hệ thống' : 'Khách'}</strong><span>·</span><time>{message.time}</time></div><div className="sw-message-bubble"><p>{message.content}</p></div></div>
        </article>
      </div>;
    })}
    {customer.messages.at(-1)?.role === 'sales' && <div className="sw-read-status"><CheckCheck size={13} />Đã lưu {customer.messages.at(-1).time}</div>}
    <div className="sw-conversation-note">Lịch sử từ hệ thống · Không đồng bộ trạng thái đã đọc từ kênh ngoài</div>
  </div>;
}

function MessageComposer({ value, onChange, onSend, inputRef, customer, sending, disabled, draft }) {
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [dismissedDraftId, setDismissedDraftId] = useState(null);
  function submit(event) {
    event.preventDefault();
    if (!value.trim() || sending || disabled) return;
    onSend(); setEmojiOpen(false);
  }
  return <form className="sw-composer" onSubmit={submit}>
    {replySuggestionsAvailable && draft.open && <DraftReply customer={customer} enabled={draft.enabled} onToggle={draft.onToggle} preferenceBusy={draft.preferenceBusy} busy={draft.busy} onGenerate={draft.onGenerate} onInsert={draft.onInsert} onDismiss={() => { setDismissedDraftId(customer.draftId); draft.onClose(); }} hasComposerText={Boolean(value.trim())} dismissed={Boolean(customer.draftId && dismissedDraftId === customer.draftId)} />}
    <div className="sw-composer-box">
      <textarea ref={inputRef} aria-label={`Tin nhắn cho ${customer.name}`} placeholder="Soạn tin lưu vào hệ thống…" rows={2} maxLength={6000} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(event); } }} />
      <div className="sw-composer-tools"><div className="sw-composer-options">
        {replySuggestionsAvailable && <button type="button" className={`sw-draft-trigger ${draft.open ? 'is-active' : ''}`} aria-label={draft.enabled ? 'Gợi ý trả lời AI' : 'Cài đặt gợi ý trả lời AI'} title={draft.enabled ? 'Tạo bản nháp khi bạn yêu cầu' : 'Gợi ý đang tắt. Mở để bật.'} aria-expanded={draft.open} disabled={disabled || draft.preferenceBusy} onClick={draft.open ? draft.onClose : draft.onOpen}><Sparkles size={17} /><span>{draft.enabled ? 'Gợi ý' : 'Bật gợi ý'}</span></button>}
        <div className="sw-emoji-wrap"><IconButton label="Chọn biểu cảm" aria-expanded={emojiOpen} disabled={disabled} onClick={() => setEmojiOpen(!emojiOpen)}><Smile size={18} /></IconButton>{emojiOpen && <div className="sw-emoji-picker">{['😊', '👍', '🙏', '🚗', '❤️'].map((emoji) => <button type="button" key={emoji} aria-label={`Thêm ${emoji}`} onClick={() => { if (value.length + emoji.length <= 6000) onChange(value + emoji); setEmojiOpen(false); inputRef.current.focus(); }}>{emoji}</button>)}</div>}</div>
        <span className="sw-composer-hint">Enter để lưu · Shift + Enter xuống dòng</span>
      </div><button className="sw-primary-button sw-send-button" type="submit" disabled={!value.trim() || sending || disabled}>{sending ? 'Đang lưu…' : 'Lưu tin'}<Send size={15} /></button></div>
    </div>
    <div className="sw-composer-footnote">Nháp tự lưu trên trình duyệt · Lưu tin chỉ ghi vào hệ thống, chưa gửi tới Zalo / Messenger.</div>
  </form>;
}

export function ConversationWorkspace({ customer, onStar, onCreateTask, highlight, composerValue, onComposerChange, onSend, composerRef, onBack, onShowTool, loading, error, onRetry, sending, onRefresh, draftOpen, onOpenDraft, onCloseDraft, draftEnabled, onToggleDraft, preferenceBusy, onGenerateDraft, draftBusy, onInsertDraft, onLoadOlder, loadingOlder, onSaveStage, stageBusy, activeTool }) {
  const [stageOpen, setStageOpen] = useState(false);
  const stageRef = useRef(null); const stageTrigger = useRef(null);
  const now = useWorkspaceClock(); const counts = taskCounts(customer.tasks, now);
  const brief = headerFacts(customer).join(' · ');
  const summaryOpen = activeTool === 'summary';
  const detailLoading = loading && !customer.loaded && !error;
  useEffect(() => {
    if (!stageOpen) return;
    stageRef.current?.querySelector('select')?.focus();
    function close(event) {
      if (event.type === 'keydown' && event.key === 'Escape') { event.preventDefault(); setStageOpen(false); stageTrigger.current?.focus(); }
      if (event.type === 'pointerdown' && !stageRef.current?.contains(event.target) && !stageTrigger.current?.contains(event.target)) setStageOpen(false);
    }
    document.addEventListener('keydown', close); document.addEventListener('pointerdown', close);
    return () => { document.removeEventListener('keydown', close); document.removeEventListener('pointerdown', close); };
  }, [stageOpen]);
  function openTool(type) { setStageOpen(false); onShowTool(type); }
  return <section className="sw-conversation" aria-label={`Không gian tư vấn ${customer.name}`}>
    <div className="sw-customer-header">
      <IconButton label="Về danh sách khách hàng" className="sw-mobile-back-button" onClick={onBack}><ArrowLeft size={17} /></IconButton>
      <button type="button" className="sw-profile-avatar" aria-label="Mở bối cảnh khách hàng" disabled={!customer.loaded} onClick={() => openTool('summary')}><Avatar customer={customer} /></button>
      <div className="sw-customer-identity"><div className="sw-customer-title"><button type="button" className="sw-customer-name" disabled={!customer.loaded} onClick={() => openTool('summary')}><h1>{customer.name}</h1></button>
        <div className="sw-stage-wrap"><button ref={stageTrigger} type="button" className="sw-stage-trigger" aria-label={`Giai đoạn: ${customer.stage}`} aria-expanded={stageOpen} disabled={!customer.loaded} onClick={() => setStageOpen(!stageOpen)}><StageBadge customer={customer} /><ChevronDown size={12} /></button>
          {stageOpen && <section className="sw-stage-popover" ref={stageRef} role="dialog" aria-label="Sửa giai đoạn"><div className="sw-inline-heading"><strong>Giai đoạn bán hàng</strong><IconButton label="Đóng giai đoạn" onClick={() => { setStageOpen(false); stageTrigger.current?.focus(); }}><X size={16} /></IconButton></div><LeadStageEditor customer={customer} busy={stageBusy} onSave={async (...args) => { await onSaveStage(...args); setStageOpen(false); stageTrigger.current?.focus(); }} /></section>}
        </div>
        <IconButton label={customer.starred ? 'Bỏ đánh dấu khách hàng' : 'Đánh dấu khách hàng'} className={customer.starred ? 'sw-starred' : ''} aria-pressed={customer.starred} onClick={onStar}><Star size={14} fill={customer.starred ? 'currentColor' : 'none'} /></IconButton>
      </div><button type="button" className="sw-customer-brief" aria-label="Xem bối cảnh khách hàng" disabled={!customer.loaded} onClick={() => openTool('summary')}><span>{brief || 'Xem nhu cầu khách hàng'}</span><span className="sw-brief-more">Xem thêm</span><ChevronRight size={12} /></button></div>
      <button type="button" className="sw-primary-button sw-create-task" aria-label="Tạo công việc" disabled={!customer.loaded} onClick={() => { setStageOpen(false); onCreateTask(); }}><Plus size={14} /><span>Tạo công việc</span></button>
    </div>
    <div className="sw-tab-panel">
      {error && <div className="sw-error-banner" role="alert"><span>{error}</span><button type="button" className="sw-text-button" onClick={onRetry}>Thử lại</button></div>}
      <div className="sw-conversation-toolbar sw-ai-toolbar"><div className="sw-conversation-tools">
        <button type="button" className={`sw-toolbar-button ${summaryOpen ? 'is-active' : ''}`} aria-expanded={summaryOpen} aria-controls="sw-conversation-summary" disabled={!customer.loaded} onClick={() => openTool(summaryOpen ? null : 'summary')}><Sparkles size={14} />Tóm tắt{customer.pendingAnalysis > 0 && <span className="sw-new-messages" title={`${customer.pendingAnalysis} tin mới chưa phân tích`}>{customer.pendingAnalysis} tin mới</span>}</button>
        <button type="button" className={`sw-toolbar-button ${activeTool === 'tasks' ? 'is-active' : ''}`} aria-expanded={activeTool === 'tasks'} title={`${counts.pending} việc chưa hoàn thành`} disabled={!customer.loaded} onClick={() => openTool('tasks')}><ListTodo size={14} />Công việc<span className="sw-tool-count">{counts.pending}</span></button>
      </div><span className="sw-conversation-channel" title="Số tin đã tải / tổng số tin lưu trong hệ thống">{customer.source} · {customer.messages.length}/{customer.messageTotal} tin</span><IconButton label="Làm mới tin nhắn" disabled={loading} onClick={onRefresh}><RefreshCw size={14} className={loading ? 'sw-spin' : ''} /></IconButton></div>
      <div className="sw-chat-surface">
        {detailLoading ? <div className="sw-detail-loading" role="status" aria-label="Đang tải hội thoại"><div className="sw-skeleton-line" />{[1, 2, 3, 4].map((id) => <div className="sw-skeleton" key={id} />)}</div> : <ConversationViewer customer={customer} highlight={highlight} onLoadOlder={onLoadOlder} loadingOlder={loadingOlder} />}
        {!activeTool && <CopilotBubble onOpen={() => openTool('copilot')} />}
      </div>
      {!detailLoading && <MessageComposer value={composerValue} onChange={onComposerChange} onSend={onSend} inputRef={composerRef} customer={customer} sending={sending} disabled={!customer.loaded} draft={{ open: draftOpen, enabled: draftEnabled, onOpen: onOpenDraft, onClose: onCloseDraft, onToggle: onToggleDraft, preferenceBusy, onGenerate: onGenerateDraft, busy: draftBusy, onInsert: onInsertDraft }} />}
    </div>
  </section>;
}
