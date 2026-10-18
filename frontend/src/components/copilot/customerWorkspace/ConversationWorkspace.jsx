import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Star, MessageSquare, Send, Sparkles, CheckCheck, ListTodo, RefreshCw, ChevronDown, X, Bot } from 'lucide-react';
import { Avatar, StageBadge, IconButton, CopilotBubble } from './WorkspacePrimitives';
import { DraftReply } from './ConversationIntelligence';
import { LeadStageEditor } from './CustomerToolsDrawer';
import { taskCounts } from './workspaceData';
import { useWorkspaceClock } from './useCustomerWorkspace';
import { replySuggestionsAvailable } from './workspaceFeatures';

function ConversationViewer({ customer, highlight, onLoadOlder, loadingOlder, onSuggestTaskFromMessage, suggestingMessageId, onAskCopilotFromMessage }) {
  const scrollRef = useRef(null);
  const messageRefs = useRef(null);
  if (!messageRefs.current) messageRefs.current = new Map();
  const [selectedMsgId, setSelectedMsgId] = useState(null);
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
      const isSuggesting = suggestingMessageId === message.id;
      const isSelected = selectedMsgId === message.id;
      return <div key={message.id}>
        {index > 0 && message.seq > customer.messages[index - 1].seq + 1 && <button type="button" className="sw-text-button sw-load-older" disabled={loadingOlder} onClick={() => load(message.seq)}>Tải phần hội thoại còn thiếu</button>}
        {(index === 0 || customer.messages[index - 1].date !== message.date) && <div className="sw-date-separator"><span>{message.date ? new Date(`${message.date}T12:00:00`).toLocaleDateString('vi-VN') : 'Chưa rõ ngày'}</span></div>}
        <article
          ref={(node) => { if (node) messageRefs.current.set(message.id, node); else messageRefs.current.delete(message.id); }}
          tabIndex={-1}
          onClick={() => setSelectedMsgId((prev) => prev === message.id ? null : message.id)}
          className={`sw-chat-message ${isSales ? 'is-sales' : 'is-customer'} ${highlight?.messageId === message.id ? 'is-highlighted' : ''} ${isSelected ? 'is-selected-msg' : ''}`}
          aria-label={`Tin nhắn ${isSales ? 'Sales' : customer.name} lúc ${message.time}`}
        >
          <Avatar customer={customer} sales={isSales} size="small" />
          <div className="sw-message-body">
            <div className="sw-message-meta">
              <strong>{isSales ? 'Sales' : message.role === 'system' ? 'Hệ thống' : 'Khách'}</strong>
              <span>·</span>
              <time>{message.time}</time>
              <div className="sw-msg-actions" onClick={(e) => e.stopPropagation()}>
                {onSuggestTaskFromMessage && (
                  <button
                    type="button"
                    className={`sw-msg-task-btn ${isSuggesting ? 'is-busy' : ''}`}
                    title="AI bóc tách và gợi ý tạo công việc từ tin nhắn này"
                    disabled={Boolean(suggestingMessageId)}
                    onClick={() => onSuggestTaskFromMessage(message)}
                  >
                    {isSuggesting ? <RefreshCw size={11} className="sw-spin" /> : <Sparkles size={11} />}
                    <span>{isSuggesting ? 'Đang tách việc…' : 'Tạo công việc'}</span>
                  </button>
                )}
                {onAskCopilotFromMessage && (
                  <button
                    type="button"
                    className="sw-msg-task-btn sw-msg-copilot-btn"
                    title="Hỏi Trợ lý Copilot về nội dung tin nhắn này"
                    onClick={() => onAskCopilotFromMessage(message)}
                  >
                    <Bot size={11} />
                    <span>Hỏi Copilot</span>
                  </button>
                )}
              </div>
            </div>
            <div className="sw-message-bubble"><p>{message.content}</p></div>
          </div>
        </article>
      </div>;
    })}
    {customer.messages.at(-1)?.role === 'sales' && <div className="sw-read-status"><CheckCheck size={13} />Đã lưu {customer.messages.at(-1).time}</div>}
  </div>;
}

function MessageComposer({ value, onChange, onSend, inputRef, customer, sending, disabled, draft }) {
  const [dismissedDraftId, setDismissedDraftId] = useState(null);
  function submit(event) {
    event.preventDefault();
    if (!value.trim() || sending || disabled) return;
    onSend();
  }
  return <form className="sw-composer" onSubmit={submit}>
    {replySuggestionsAvailable && draft.open && (
      <DraftReply
        customer={customer}
        busy={draft.busy}
        onGenerate={() => { setDismissedDraftId(null); draft.onGenerate(); }}
        onInsert={draft.onInsert}
        onDismiss={() => { setDismissedDraftId(customer.draftId); draft.onClose(); }}
        hasComposerText={Boolean(value.trim())}
        dismissed={Boolean(customer.draftId && dismissedDraftId === customer.draftId)}
      />
    )}
    <div className="sw-composer-box">
      <textarea ref={inputRef} aria-label={`Tin nhắn cho ${customer.name}`} placeholder="Soạn tin nhắn" rows={1} maxLength={6000} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(event); } }} />
      <div className="sw-composer-tools">
        {replySuggestionsAvailable && (
          <button
            type="button"
            className={`sw-draft-trigger ${draft.open ? 'is-active' : ''}`}
            aria-label="Gợi ý trả lời AI"
            title="AI đọc lịch sử hội thoại và tài liệu VinFast để gợi ý câu trả lời cho tin nhắn mới nhất của khách"
            aria-expanded={draft.open}
            disabled={disabled || !customer.messages.length}
            onClick={() => {
              if (draft.open) {
                draft.onClose();
              } else {
                setDismissedDraftId(null);
                draft.onOpen();
              }
            }}
          >
            {draft.busy ? <RefreshCw size={14} className="sw-spin" /> : <Sparkles size={15} />}
            <span>{draft.busy ? 'Đang gợi ý…' : 'Gợi ý trả lời'}</span>
          </button>
        )}
        <button className="sw-primary-button sw-send-button" type="submit" aria-label={sending ? 'Đang lưu tin nhắn' : 'Lưu tin nhắn'} disabled={!value.trim() || sending || disabled}><Send size={15} /></button>
      </div>
    </div>
  </form>;
}

export function ConversationWorkspace({ customer, onStar, highlight, composerValue, onComposerChange, onSend, composerRef, onBack, onShowTool, loading, error, onRetry, sending, onRefresh, draftOpen, onOpenDraft, onCloseDraft, draftEnabled, onToggleDraft, preferenceBusy, onGenerateDraft, draftBusy, onInsertDraft, onLoadOlder, loadingOlder, onSaveStage, stageBusy, activeTool, onAnalyze, analyzing, onSuggestTaskFromMessage, suggestingMessageId, onAskCopilotFromMessage }) {
  const [stageOpen, setStageOpen] = useState(false);
  const stageRef = useRef(null); const stageTrigger = useRef(null);
  const now = useWorkspaceClock(); const counts = taskCounts(customer.tasks, now);
  const summaryOpen = ['summary', 'profile', 'activities'].includes(activeTool);
  const tasksOpen = activeTool === 'tasks';
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
      <button type="button" className="sw-profile-avatar" aria-label="Mở bối cảnh khách hàng" disabled={!customer.loaded} onClick={() => openTool(summaryOpen ? null : 'summary')}><Avatar customer={customer} /></button>
      <div className="sw-customer-identity"><div className="sw-customer-title"><button type="button" className="sw-customer-name" disabled={!customer.loaded} onClick={() => openTool(summaryOpen ? null : 'summary')}><h1>{customer.name}</h1></button>
        <div className="sw-stage-wrap"><button ref={stageTrigger} type="button" className="sw-stage-trigger" aria-label={`Giai đoạn: ${customer.stage}`} aria-expanded={stageOpen} disabled={!customer.loaded} onClick={() => setStageOpen(!stageOpen)}><StageBadge customer={customer} /><ChevronDown size={12} /></button>
          {stageOpen && <section className="sw-stage-popover" ref={stageRef} role="dialog" aria-label="Sửa giai đoạn"><div className="sw-inline-heading"><strong>Giai đoạn bán hàng</strong><IconButton label="Đóng giai đoạn" onClick={() => { setStageOpen(false); stageTrigger.current?.focus(); }}><X size={16} /></IconButton></div><LeadStageEditor customer={customer} busy={stageBusy} onSave={async (...args) => { await onSaveStage(...args); setStageOpen(false); stageTrigger.current?.focus(); }} /></section>}
        </div>
        <IconButton label={customer.starred ? 'Bỏ đánh dấu khách hàng' : 'Đánh dấu khách hàng'} className={customer.starred ? 'sw-starred' : ''} aria-pressed={customer.starred} onClick={onStar}><Star size={14} fill={customer.starred ? 'currentColor' : 'none'} /></IconButton>
      </div></div>
    </div>
    <div className="sw-tab-panel">
      {error && <div className="sw-error-banner" role="alert"><span>{error}</span><button type="button" className="sw-text-button" onClick={onRetry}>Thử lại</button></div>}
      <div className="sw-conversation-toolbar sw-ai-toolbar"><div className="sw-conversation-tools">
        <button type="button" className={`sw-toolbar-button ${summaryOpen ? 'is-active' : ''}`} aria-expanded={summaryOpen} aria-controls="sw-conversation-summary" disabled={!customer.loaded} onClick={() => openTool(summaryOpen ? null : 'summary')}><Sparkles size={14} />Tóm tắt</button>
        <button type="button" className={`sw-toolbar-button ${tasksOpen ? 'is-active' : ''}`} aria-expanded={tasksOpen} title={`${counts.pending} việc chưa hoàn thành`} disabled={!customer.loaded} onClick={() => openTool(tasksOpen ? null : 'tasks')}><ListTodo size={14} />Công việc<span className="sw-tool-count">{counts.pending}</span></button>
        {(customer.pendingAnalysis > 0 || analyzing) && <button type="button" className={`sw-toolbar-button sw-toolbar-analyze-btn ${analyzing ? 'is-running' : ''}`} disabled={!customer.loaded || analyzing} title={analyzing ? 'AI đang phân tích hội thoại này' : `Chạy AI phân tích ${customer.pendingAnalysis} tin nhắn mới`} onClick={() => { openTool('summary'); onAnalyze?.(); }}><RefreshCw size={13} className={analyzing ? 'sw-spin' : ''} /><span>{analyzing ? 'Đang phân tích…' : 'Phân tích ngay'}</span>{!analyzing && customer.pendingAnalysis > 0 && <span className="sw-new-messages">{customer.pendingAnalysis} tin mới</span>}</button>}
      </div><span className="sw-conversation-channel" title="Số tin đã tải / tổng số tin lưu trong hệ thống">{customer.messages.length}/{customer.messageTotal} tin</span><IconButton label="Làm mới tin nhắn" disabled={loading} onClick={onRefresh}><RefreshCw size={14} className={loading ? 'sw-spin' : ''} /></IconButton></div>
      <div className="sw-chat-surface">
        {detailLoading ? <div className="sw-detail-loading" role="status" aria-label="Đang tải hội thoại"><div className="sw-skeleton-line" />{[1, 2, 3, 4].map((id) => <div className="sw-skeleton" key={id} />)}</div> : <ConversationViewer customer={customer} highlight={highlight} onLoadOlder={onLoadOlder} loadingOlder={loadingOlder} onSuggestTaskFromMessage={onSuggestTaskFromMessage} suggestingMessageId={suggestingMessageId} onAskCopilotFromMessage={onAskCopilotFromMessage} />}
      </div>
      {!activeTool && <CopilotBubble onOpen={() => openTool('copilot')} />}
      {!detailLoading && <MessageComposer value={composerValue} onChange={onComposerChange} onSend={onSend} inputRef={composerRef} customer={customer} sending={sending} disabled={!customer.loaded} draft={{ open: draftOpen, enabled: draftEnabled, onOpen: onOpenDraft, onClose: onCloseDraft, onToggle: onToggleDraft, preferenceBusy, onGenerate: onGenerateDraft, busy: draftBusy, onInsert: onInsertDraft }} />}
    </div>
  </section>;
}
