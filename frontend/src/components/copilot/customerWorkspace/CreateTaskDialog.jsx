import { useEffect, useState } from 'react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { DetailDialog } from './WorkspacePrimitives';
import { formatDateTime, localInput, toUTC } from '../agenda/agendaData';

export function CreateTaskDialog({ customer, customers = [], onClose, onCreate }) {
  return <DetailDialog title="Tạo công việc / lịch hẹn" onClose={onClose}><TaskEditor customer={customer} customers={customers} onSave={onCreate} onCancel={onClose} /></DetailDialog>;
}

export function TaskEditor({ task, customer, customers = [], onSave, onCancel }) {
  const [title, setTitle] = useState(task?.title || '');
  const [priority, setPriority] = useState(task?.priority === 'urgent' ? 'high' : task?.priority || 'medium');
  const [start, setStart] = useState(() => localInput(task?.starts_at));
  const [end, setEnd] = useState(() => localInput(task?.ends_at));
  const [kind, setKind] = useState(task?.item_type || 'task');
  const [description, setDescription] = useState(task?.description || '');
  const [customerId, setCustomerId] = useState(task?.customer_id || customer?.customerId || '');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [overlaps, setOverlaps] = useState([]); const [conflictError, setConflictError] = useState('');
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      if (!start || !end || end <= start) { setOverlaps([]); setConflictError(''); return; }
      salesCopilotApi.getTaskOverlaps({ starts_at: toUTC(start), ends_at: toUTC(end), ...(task?.id ? { exclude_id: task.id } : {}) }).then((items) => { if (!cancelled) { setOverlaps(items); setConflictError(''); } }).catch(() => { if (!cancelled) { setOverlaps([]); setConflictError('Chưa kiểm tra được lịch trùng. Bạn vẫn có thể lưu.'); } });
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [start, end, task?.id]);
  return <form className="sw-task-form sw-task-editor" onSubmit={async (event) => {
    event.preventDefault(); if (busy || !title.trim()) return;
    if (!start || !end || end <= start) { setError('Cần chọn giờ kết thúc sau giờ bắt đầu.'); return; }
    setBusy(true); setError('');
    try { await onSave({ title: title.trim(), priority, description: description.trim(), item_type: kind, starts_at: toUTC(start), ends_at: toUTC(end), ...(!task ? { customer_id: customerId || null } : {}), ...(task?.status === 'needs_review' ? { status: 'pending' } : {}) }); }
    catch (failure) { setError(typeof failure.message === 'string' ? failure.message : 'Chưa lưu được công việc.'); setBusy(false); }
  }}>
    <h3>{task?.status === 'needs_review' ? 'Xác nhận và xếp lịch' : task ? 'Sửa công việc / lịch hẹn' : 'Tạo công việc / lịch hẹn'}</h3>
    <label>Loại mục<select value={kind} onChange={(event) => setKind(event.target.value)}><option value="task">Công việc</option><option value="appointment">Lịch hẹn</option></select></label>
    <label>Tiêu đề *<input autoFocus required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ví dụ: Gọi tư vấn, hẹn lái thử" /></label>
    {task ? <p className="sw-secondary">{customer?.name || task.customer_name || 'Công việc / lịch hẹn cá nhân'}</p> : <label>Khách hàng<select value={customerId} onChange={(event) => setCustomerId(event.target.value)}><option value="">Cá nhân · Không gắn khách hàng</option>{(customer ? [{ customer_id: customer.customerId, customer_name: customer.name }] : customers).map((item) => <option key={item.customer_id} value={item.customer_id}>{item.customer_name}</option>)}</select></label>}
    <label>Bắt đầu *<input type="datetime-local" required value={start} onInput={(event) => setStart(event.target.value)} onChange={(event) => setStart(event.target.value)} /></label>
    <label>Kết thúc *<input type="datetime-local" required value={end} onInput={(event) => setEnd(event.target.value)} onChange={(event) => setEnd(event.target.value)} /></label>
    <small className="sw-secondary">Giờ Việt Nam (UTC+7)</small>
    {overlaps.length > 0 && <p className="sw-info-note" role="status">Trùng giờ với {overlaps.length} mục: {overlaps.slice(0, 3).map((item) => `${item.title} (${formatDateTime(item.starts_at)})`).join('; ')}. Bạn vẫn có thể lưu.</p>}
    {conflictError && <p className="sw-info-note" role="status">{conflictError}</p>}
    <label>Mức ưu tiên<select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="low">Thấp</option><option value="medium">Trung bình</option><option value="high">Cao</option></select></label>
    <label>Ghi chú<textarea rows={3} maxLength={4000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
    {error && <p className="sw-error-banner" role="alert">{error}</p>}
    <div className="sw-inline-actions"><button type="button" className="sw-text-button" disabled={busy} onClick={onCancel}>Hủy</button><button type="submit" className="sw-primary-button" disabled={busy || !title.trim() || !start || !end || end <= start}>{busy ? 'Đang lưu…' : task?.status === 'needs_review' ? 'Duyệt và xếp lịch' : 'Lưu'}</button></div>
  </form>;
}
