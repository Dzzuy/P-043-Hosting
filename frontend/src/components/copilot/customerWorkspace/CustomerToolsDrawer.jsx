import { useEffect, useState } from 'react';
import { AlertTriangle, Check, ChevronRight, Clock3, MapPin, Plus, RefreshCw, Sparkles } from 'lucide-react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { ContextDrawerHost } from './WorkspacePrimitives';
import { leadStages, taskCounts, taskGroups } from './workspaceData';
import { defaultTaskWindow, formatDateTime, itemLabel, localInput, toUTC } from '../agenda/agendaData';
import { CustomerKnowledgeTool } from './CustomerKnowledgeTool';
import { TaskEditor } from './CreateTaskDialog';
import { useWorkspaceClock } from './useCustomerWorkspace';
import { ConversationSummary } from './ConversationIntelligence';

export function Activities({ customer, onSourceClick }) {
  return <section className="sw-activities"><h3>Mốc chăm sóc</h3><p className="sw-secondary">Sự kiện đã trích xuất từ hội thoại.</p>{!customer.events.length && <p className="sw-info-note">Chưa có mốc chăm sóc được lưu.</p>}<div className="sw-detail-timeline">{customer.events.map((event) => <div className="sw-activity" key={event.id}><small>{event.time}</small><strong>{event.text}</strong>{event.sourceMessageId ? <button type="button" className="sw-text-button" onClick={() => onSourceClick(event.sourceMessageId)}>Xem tin nguồn<ChevronRight size={12} /></button> : <small>Chưa có liên kết nguồn</small>}</div>)}</div></section>;
}

function MessageTaskSuggestionsPanel({ customer, suggestionState, onDismiss, onSaveBatch }) {
  const [items, setItems] = useState([]);
  const [expandedIdx, setExpandedIdx] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [conflicts, setConflicts] = useState([]);

  useEffect(() => {
    const raw = suggestionState?.tasks || [];
    setItems(raw.map((t, idx) => {
      const fallback = defaultTaskWindow(t.item_type || 'task', idx * 30);
      return {
        selected: true,
        title: t.title || '',
        item_type: t.item_type || 'task',
        priority: t.priority || 'medium',
        start: localInput(t.starts_at) || fallback.start,
        end: localInput(t.ends_at) || fallback.end,
        location: t.location || (t.item_type === 'appointment' ? 'Showroom VinFast' : ''),
        description: t.description || '',
        source_message_ids: t.source_message_ids || (suggestionState?.message?.id ? [suggestionState.message.id] : []),
      };
    }));
    setExpandedIdx(raw.length === 1 ? 0 : null);
    setError('');
    setConflicts([]);
  }, [suggestionState]);

  if (!suggestionState) return null;

  if (suggestionState.loading) {
    return <section className="sw-ai-task-suggestions is-loading" role="status">
      <div className="sw-ai-task-head">
        <strong><RefreshCw size={13} className="sw-spin" /> AI đang bóc tách công việc từ tin nhắn…</strong>
        <button type="button" className="sw-text-button" onClick={onDismiss}>Đóng</button>
      </div>
      {suggestionState.message?.content && <blockquote className="sw-ai-task-quote">“{suggestionState.message.content}”</blockquote>}
    </section>;
  }

  if (suggestionState.error) {
    return <section className="sw-ai-task-suggestions">
      <div className="sw-ai-task-head">
        <strong><Sparkles size={13} /> Gợi ý công việc từ tin nhắn</strong>
        <button type="button" className="sw-text-button" onClick={onDismiss}>Đóng</button>
      </div>
      <p className="sw-error-banner" role="alert">{suggestionState.error}</p>
    </section>;
  }

  const selectedItems = items.filter((item) => item.selected);

  function updateItem(idx, patch) {
    setConflicts([]);
    setItems((prev) => prev.map((item, i) => i === idx ? { ...item, ...patch } : item));
  }

  async function handleSaveAll(forceOverlap = false) {
    if (!selectedItems.length || saving) return;
    for (const item of selectedItems) {
      if (!item.title.trim()) {
        setError('Tiêu đề công việc không được để trống.');
        return;
      }
      if (!item.start || !item.end || item.end <= item.start) {
        setError(`Mục "${item.title}": Cần chọn giờ bắt đầu và kết thúc hợp lệ để hiển thị trên thời khóa biểu.`);
        return;
      }
      if (item.item_type === 'appointment' && !item.location.trim()) {
        setError(`Lịch hẹn "${item.title}" cần có địa điểm.`);
        return;
      }
    }
    setSaving(true);
    setError('');
    try {
      if (!forceOverlap) {
        const foundConflicts = [];
        for (const item of selectedItems) {
          try {
            const existing = await salesCopilotApi.getTaskOverlaps({
              starts_at: toUTC(item.start),
              ends_at: toUTC(item.end),
            });
            for (const ov of existing || []) {
              foundConflicts.push({
                newTitle: item.title,
                existingTitle: ov.title,
                starts_at: ov.starts_at,
                ends_at: ov.ends_at,
              });
            }
          } catch {
            // Ignore overlap check network failure and proceed
          }
        }
        for (let i = 0; i < selectedItems.length; i += 1) {
          for (let j = i + 1; j < selectedItems.length; j += 1) {
            const a = selectedItems[i];
            const b = selectedItems[j];
            if (a.start < b.end && a.end > b.start) {
              foundConflicts.push({
                newTitle: a.title,
                existingTitle: `${b.title} (cùng đợt tạo)`,
                starts_at: toUTC(b.start),
                ends_at: toUTC(b.end),
              });
            }
          }
        }
        if (foundConflicts.length > 0) {
          setConflicts(foundConflicts);
          setSaving(false);
          return;
        }
      }

      const payloads = selectedItems.map((item) => ({
        title: item.title.trim(),
        item_type: item.item_type,
        priority: item.priority,
        starts_at: toUTC(item.start),
        ends_at: toUTC(item.end),
        location: item.location.trim(),
        description: item.description.trim(),
        source_message_ids: item.source_message_ids,
        customer_id: customer?.customerId,
      }));
      await onSaveBatch(payloads);
    } catch (failure) {
      setError(failure.message || 'Chưa lưu được công việc.');
      setSaving(false);
    }
  }

  return <section className="sw-ai-task-suggestions" aria-label="Gợi ý công việc từ tin nhắn">
    <div className="sw-ai-task-head">
      <strong><Sparkles size={13} /> AI gợi ý {items.length} việc từ tin nhắn</strong>
      <button type="button" className="sw-text-button" disabled={saving} onClick={onDismiss}>Bỏ qua</button>
    </div>
    {suggestionState.message?.content && <blockquote className="sw-ai-task-quote">“{suggestionState.message.content}”</blockquote>}
    <div className="sw-ai-task-list">
      {items.map((item, idx) => {
        const isExpanded = expandedIdx === idx;
        return <article key={idx} className={`sw-ai-task-item ${item.selected ? 'is-selected' : ''}`}>
          <div className="sw-ai-task-item-top">
            <label className="sw-task-check">
              <input type="checkbox" checked={item.selected} disabled={saving} onChange={(e) => updateItem(idx, { selected: e.target.checked })} />
              <span>{item.selected && <Check size={12} />}</span>
              <strong>{item.title || 'Chưa có tiêu đề'}</strong>
            </label>
            <button type="button" className="sw-text-button" onClick={() => setExpandedIdx(isExpanded ? null : idx)}>{isExpanded ? 'Thu gọn' : 'Sửa giờ / chi tiết'}</button>
          </div>
          <div className="sw-task-meta">
            <span><Clock3 size={12} />{item.start && item.end ? `${formatDateTime(toUTC(item.start))} – ${formatDateTime(toUTC(item.end))}` : 'Chưa xếp giờ cụ thể'}</span>
            <span>{item.item_type === 'appointment' ? 'Lịch hẹn' : 'Công việc'}</span>
            <span className={`sw-priority sw-priority-${item.priority}`}>{item.priority === 'high' ? 'Cao' : item.priority === 'medium' ? 'Trung bình' : 'Thấp'}</span>
          </div>
          {item.location && !isExpanded && <p className="sw-ai-task-sub"><MapPin size={11} /> {item.location}</p>}
          {item.description && !isExpanded && <p className="sw-task-description">{item.description}</p>}
          {isExpanded && (
            <div className="sw-ai-task-edit-fields">
              <label>Tiêu đề *<input type="text" maxLength={200} value={item.title} onChange={(e) => updateItem(idx, { title: e.target.value })} /></label>
              <div className="sw-ai-task-row-2">
                <label>Loại mục<select value={item.item_type} onChange={(e) => updateItem(idx, { item_type: e.target.value })}><option value="task">Công việc</option><option value="appointment">Lịch hẹn</option></select></label>
                <label>Mức ưu tiên<select value={item.priority} onChange={(e) => updateItem(idx, { priority: e.target.value })}><option value="low">Thấp</option><option value="medium">Trung bình</option><option value="high">Cao</option></select></label>
              </div>
              <div className="sw-ai-task-row-2">
                <label>Bắt đầu *<input type="datetime-local" required value={item.start} onChange={(e) => updateItem(idx, { start: e.target.value })} /></label>
                <label>Kết thúc *<input type="datetime-local" required value={item.end} onChange={(e) => updateItem(idx, { end: e.target.value })} /></label>
              </div>
              <label>Địa điểm{item.item_type === 'appointment' ? ' *' : ''}<input type="text" maxLength={1000} value={item.location} onChange={(e) => updateItem(idx, { location: e.target.value })} /></label>
              <label>Ghi chú<textarea rows={2} maxLength={4000} value={item.description} onChange={(e) => updateItem(idx, { description: e.target.value })} /></label>
            </div>
          )}
        </article>;
      })}
    </div>
    {conflicts.length > 0 && (
      <div className="sw-overlap-confirm-box" role="alert">
        <strong><AlertTriangle size={14} /> Khung giờ này đã có lịch trên Thời khóa biểu!</strong>
        <ul>
          {conflicts.map((c, i) => (
            <li key={i}>
              <strong>{c.newTitle}</strong> trùng giờ với: <strong>{c.existingTitle}</strong> ({formatDateTime(c.starts_at)} – {formatDateTime(c.ends_at, false)})
            </li>
          ))}
        </ul>
        <p>Bạn vẫn muốn thêm vào cùng khung giờ chứ?</p>
        <div className="sw-inline-actions">
          <button type="button" className="sw-secondary-button" disabled={saving} onClick={() => setConflicts([])}>Đổi giờ khác</button>
          <button type="button" className="sw-primary-button" disabled={saving} onClick={() => void handleSaveAll(true)}>{saving ? 'Đang lưu…' : 'Vẫn thêm vào lịch'}</button>
        </div>
      </div>
    )}
    {error && <p className="sw-error-banner" role="alert">{error}</p>}
    {!conflicts.length && (
      <div className="sw-inline-actions">
        <button type="button" className="sw-text-button" disabled={saving} onClick={onDismiss}>Hủy</button>
        <button type="button" className="sw-primary-button" disabled={saving || !selectedItems.length} onClick={() => void handleSaveAll(false)}>
          {saving ? 'Đang kiểm tra lịch…' : `Lưu ${selectedItems.length} việc đã chọn`}
        </button>
      </div>
    )}
  </section>;
}

function Tasks({ customer, onToggle, onCreate, busy, ownerId, creating, onCancelCreate, onSaveCreate, onEdit, onSourceClick, highlightedTaskId, suggestionState, onDismissSuggestions, onSaveSuggestedBatch }) {
  const now = useWorkspaceClock(); const counts = taskCounts(customer.tasks, now);
  const [editing, setEditing] = useState(null);
  const [actionError, setActionError] = useState('');
  useEffect(() => { if (highlightedTaskId) document.getElementById(`task-${highlightedTaskId}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, [highlightedTaskId, customer.tasks]);
  return <div className="sw-tasks-content">
    {actionError && <p className="sw-error-banner" role="alert">{actionError}</p>}
    <MessageTaskSuggestionsPanel customer={customer} suggestionState={suggestionState} onDismiss={onDismissSuggestions} onSaveBatch={onSaveSuggestedBatch} />
    <div className="sw-inline-heading"><strong>{counts.pending} việc chưa hoàn thành</strong>{!creating && <button type="button" className="sw-secondary-button" onClick={onCreate}><Plus size={13} />Tạo việc</button>}</div>
    {counts.overdue > 0 && <p className="sw-freshness">{counts.overdue} việc cần cập nhật trạng thái.</p>}
    {creating && <TaskEditor customer={customer} onSave={onSaveCreate} onCancel={onCancelCreate} />}
    {!customer.tasks.length && !creating && !suggestionState && <div className="sw-empty"><Check size={24} /><strong>Chưa có công việc được lưu</strong></div>}
    {taskGroups(customer.tasks, now).filter((group) => group.tasks.length).map((group) => <section className="sw-task-group" key={group.id}><h3>{group.label} <span>({group.tasks.length})</span></h3>{group.tasks.map((task) => <div id={`task-${task.id}`} key={task.id} className={`sw-task-row ${task.completed ? 'is-completed' : ''} ${highlightedTaskId === task.id ? 'agenda-highlight-task' : ''}`}>
      {editing === task.id ? <TaskEditor task={task} customer={customer} onCancel={() => setEditing(null)} onSave={async (changes) => { await onEdit(task.id, changes); setEditing(null); }} /> : <>
        <label className="sw-task-check"><input aria-label={`${task.completed ? 'Mở lại' : 'Hoàn thành'}: ${task.title}`} type="checkbox" checked={task.completed} disabled={busy[task.id] || task.status === 'needs_review'} onChange={() => onToggle(task.id)} /><span>{task.completed && <Check size={12} />}</span><strong>{task.title}</strong></label>
        {task.description && <p className="sw-task-description">{task.description}</p>}
        <div className="sw-task-meta"><span><Clock3 size={12} />{task.starts_at ? `${formatDateTime(task.starts_at)} – ${formatDateTime(task.ends_at)}` : 'Cần xếp lịch'}</span><span>{itemLabel(task)}</span><span className={`sw-priority sw-priority-${task.priority}`}>{['high', 'urgent'].includes(task.priority) ? 'Cao' : task.priority === 'medium' ? 'Trung bình' : 'Thấp'}</span></div>
        <p className="sw-task-origin">{task.manual ? 'Thủ công' : 'AI đề xuất'} · Phụ trách: {task.ownerId === ownerId ? 'Bạn' : task.ownerId || 'Chưa phân công'}{task.status === 'needs_review' && ' · Cần duyệt'}</p>
        <div className="sw-task-actions">{task.sourceMessageIds.map((id, index) => <button type="button" key={id} className="sw-text-button" onClick={() => onSourceClick(id)}>Tin nguồn {index + 1}</button>)}<button type="button" className="sw-text-button" onClick={() => setEditing(task.id)}>Sửa công việc</button>{task.status === 'needs_review' && <button type="button" className="sw-secondary-button" disabled={busy[task.id]} onClick={() => setEditing(task.id)}>Duyệt và xếp lịch</button>}<button type="button" className="sw-text-button" disabled={busy[task.id]} onClick={async () => { setActionError(''); try { await onEdit(task.id, { status: 'cancelled' }); } catch (error) { setActionError(error.message); } }}>Hủy mục</button></div>
      </>}
    </div>)}</section>)}
  </div>;
}

export function LeadStageEditor({ customer, busy, onSave }) {
  const [stage, setStage] = useState(leadStages.some((s) => s.id === customer.stageId) ? customer.stageId : ''); const [reason, setReason] = useState(''); const [error, setError] = useState('');
  const lead = customer.lead;
  async function save(value) { setError(''); try { await onSave(value, reason); } catch (failure) { setError(failure.message); } }
  return <div className="sw-stage-editor"><p className="sw-secondary">{lead.stage_source === 'sales' ? 'Sales đã chọn' : ['ai', 'rules'].includes(lead.stage_source) ? 'Suy ra từ bằng chứng' : 'Chưa phân tích'} · {customer.stage}</p>
    {lead.rationale && <p className="sw-secondary">Căn cứ: {lead.rationale}</p>}
    {lead.evidence?.map((e, i) => <details key={i}><summary>Bằng chứng {i + 1}</summary><blockquote>{e.quote}</blockquote></details>)}
    {lead.override?.reason && <p className="sw-secondary">Ghi chú: {lead.override.reason}</p>}
    <form className="sw-task-form" onSubmit={(event) => { event.preventDefault(); void save(stage); }}>
      <label>Giai đoạn bán hàng<select required value={stage} disabled={busy} onChange={(event) => setStage(event.target.value)}><option value="" disabled>Cần xác nhận giai đoạn</option>{leadStages.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <label>Lý do / bằng chứng (bắt buộc khi đóng cơ hội)<textarea required={['won', 'lost'].includes(stage)} rows={2} maxLength={400} value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label>
      <p className="sw-secondary">AI không ghi đè giai đoạn sales chọn.</p>{error && <p className="sw-freshness" role="alert">{error}</p>}
      <div className="sw-inline-actions">{lead.stage_source === 'sales' ? <button type="button" className="sw-text-button" disabled={busy} onClick={() => save(null)}>Dùng lại đề xuất AI</button> : <span />}<button type="submit" className="sw-primary-button" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu giai đoạn'}</button></div>
    </form></div>;
}

export function CustomerToolsDrawer({ onOpenDocument, type, customer, onClose, onSourceClick, onToggleTask, onCreateTask, taskBusy, knowledge, onSearch, onLoadHistory, onQueryChange, ownerId, onEditTask, onConfirmFact, creatingTask, onCancelCreate, onCreate, highlightedTaskId, onAnalyze, analyzing, analysisChanges, onShowTool, suggestionState, onDismissSuggestions, onSaveSuggestedBatch }) {
  const title = { profile: 'Bối cảnh khách hàng', activities: 'Mốc chăm sóc', tasks: 'Công việc', copilot: 'Trợ lý Copilot', summary: 'Bối cảnh khách hàng' }[type];
  return <ContextDrawerHost title={title} onClose={onClose}>
    {['summary', 'profile'].includes(type) && <ConversationSummary customer={customer} onAnalyze={onAnalyze} analyzing={analyzing} changes={analysisChanges} onSourceClick={onSourceClick} onConfirmFact={onConfirmFact} onHistory={() => onShowTool('activities')} />}
    {type === 'activities' && <Activities customer={customer} onSourceClick={onSourceClick} />}
    {type === 'tasks' && <Tasks customer={customer} onToggle={onToggleTask} onCreate={onCreateTask} busy={taskBusy} ownerId={ownerId} creating={creatingTask} onCancelCreate={onCancelCreate} onSaveCreate={onCreate} onEdit={onEditTask} onSourceClick={onSourceClick} highlightedTaskId={highlightedTaskId} suggestionState={suggestionState} onDismissSuggestions={onDismissSuggestions} onSaveSuggestedBatch={onSaveSuggestedBatch} />}
    {type === 'copilot' && <CustomerKnowledgeTool onOpenDocument={onOpenDocument} lookup={knowledge} onSearch={onSearch} onLoadHistory={onLoadHistory} onQueryChange={onQueryChange} />}
  </ContextDrawerHost>;
}

