import { useState } from 'react';
import { Check, ChevronRight, Clock3, Plus } from 'lucide-react';
import { ContextDrawerHost } from './WorkspacePrimitives';
import { leadStages, taskCounts, taskGroups } from './workspaceData';
import { formatDateTime, itemLabel } from '../agenda/agendaData';
import { useEffect } from 'react';
import { CustomerKnowledgeTool } from './CustomerKnowledgeTool';
import { TaskEditor } from './CreateTaskDialog';
import { useWorkspaceClock } from './useCustomerWorkspace';
import { ConversationSummary } from './ConversationIntelligence';

export function Activities({ customer, onSourceClick }) {
  return <section className="sw-activities"><h3>Mốc chăm sóc</h3><p className="sw-secondary">Sự kiện đã trích xuất từ hội thoại.</p>{!customer.events.length && <p className="sw-info-note">Chưa có mốc chăm sóc được lưu.</p>}<div className="sw-detail-timeline">{customer.events.map((event) => <div className="sw-activity" key={event.id}><small>{event.time}</small><strong>{event.text}</strong>{event.sourceMessageId ? <button type="button" className="sw-text-button" onClick={() => onSourceClick(event.sourceMessageId)}>Xem tin nguồn<ChevronRight size={12} /></button> : <small>Chưa có liên kết nguồn</small>}</div>)}</div></section>;
}

function Tasks({ customer, onToggle, onCreate, busy, ownerId, creating, onCancelCreate, onSaveCreate, onEdit, onSourceClick, highlightedTaskId }) {
  const now = useWorkspaceClock(); const counts = taskCounts(customer.tasks, now);
  const [editing, setEditing] = useState(null);
  const [actionError, setActionError] = useState('');
  useEffect(() => { if (highlightedTaskId) document.getElementById(`task-${highlightedTaskId}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, [highlightedTaskId, customer.tasks]);
  return <div className="sw-tasks-content">
    {actionError && <p className="sw-error-banner" role="alert">{actionError}</p>}
    <div className="sw-inline-heading"><strong>{counts.pending} việc chưa hoàn thành</strong>{!creating && <button type="button" className="sw-secondary-button" onClick={onCreate}><Plus size={13} />Tạo việc</button>}</div>
    {counts.overdue > 0 && <p className="sw-freshness">{counts.overdue} việc cần cập nhật trạng thái.</p>}
    {creating && <TaskEditor customer={customer} onSave={onSaveCreate} onCancel={onCancelCreate} />}
    {!customer.tasks.length && !creating && <div className="sw-empty"><Check size={24} /><strong>Chưa có công việc được lưu</strong></div>}
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
  const [stage, setStage] = useState(customer.stageId); const [reason, setReason] = useState(''); const [error, setError] = useState('');
  const lead = customer.lead;
  async function save(value) { setError(''); try { await onSave(value, reason); } catch (failure) { setError(failure.message); } }
  return <div className="sw-stage-editor"><p className="sw-secondary">{lead.stage_source === 'sales' ? 'Sales đã chọn' : lead.stage_source === 'ai' ? 'AI đề xuất' : 'Chưa phân tích'} · {customer.stage}</p>
    {lead.override?.reason && <p className="sw-secondary">Ghi chú: {lead.override.reason}</p>}
    <form className="sw-task-form" onSubmit={(event) => { event.preventDefault(); void save(stage); }}>
      <label>Giai đoạn bán hàng<select value={stage} disabled={busy} onChange={(event) => setStage(event.target.value)}>{leadStages.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <label>Ghi chú (không bắt buộc)<textarea rows={2} maxLength={400} value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label>
      <p className="sw-secondary">AI không ghi đè giai đoạn sales chọn.</p>{error && <p className="sw-freshness" role="alert">{error}</p>}
      <div className="sw-inline-actions">{lead.stage_source === 'sales' ? <button type="button" className="sw-text-button" disabled={busy} onClick={() => save(null)}>Dùng lại đề xuất AI</button> : <span />}<button type="submit" className="sw-primary-button" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu giai đoạn'}</button></div>
    </form></div>;
}

export function CustomerToolsDrawer({ type, customer, onClose, onSourceClick, onToggleTask, onCreateTask, taskBusy, knowledge, onSearch, onLoadHistory, onQueryChange, ownerId, onEditTask, onConfirmFact, creatingTask, onCancelCreate, onCreate, highlightedTaskId, onAnalyze, analyzing, analysisChanges, onShowTool }) {
  const title = { profile: 'Bối cảnh khách hàng', activities: 'Mốc chăm sóc', tasks: 'Công việc', copilot: 'Trợ lý Copilot', summary: 'Bối cảnh khách hàng' }[type];
  return <ContextDrawerHost title={title} onClose={onClose}>
    {['summary', 'profile'].includes(type) && <ConversationSummary customer={customer} onAnalyze={onAnalyze} analyzing={analyzing} changes={analysisChanges} onSourceClick={onSourceClick} onConfirmFact={onConfirmFact} onHistory={() => onShowTool('activities')} />}
    {type === 'activities' && <Activities customer={customer} onSourceClick={onSourceClick} />}
    {type === 'tasks' && <Tasks customer={customer} onToggle={onToggleTask} onCreate={onCreateTask} busy={taskBusy} ownerId={ownerId} creating={creatingTask} onCancelCreate={onCancelCreate} onSaveCreate={onCreate} onEdit={onEditTask} onSourceClick={onSourceClick} highlightedTaskId={highlightedTaskId} />}
    {type === 'copilot' && <CustomerKnowledgeTool lookup={knowledge} onSearch={onSearch} onLoadHistory={onLoadHistory} onQueryChange={onQueryChange} />}
  </ContextDrawerHost>;
}
