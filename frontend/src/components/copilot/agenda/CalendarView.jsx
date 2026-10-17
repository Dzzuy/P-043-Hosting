import { useEffect, useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { DetailDialog } from '../customerWorkspace/WorkspacePrimitives';
import { useWorkspaceClock } from '../customerWorkspace/useCustomerWorkspace';
import { addDays, dateKey, formatDateTime, itemLabel, layoutDay, localInput, mondayOf, taskState } from './agendaData';
import { useAgendaResource } from './agendaResource';

const weekdays = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật'];
export function CalendarView({ currentUser, active, week, onWeekChange: setWeek, onCustomer, onTask }) {
  const [selected, setSelected] = useState(null);
  const scrollRef = useRef(null);
  const now = useWorkspaceClock(); const today = dateKey(new Date(now).toISOString());
  const timeNow = localInput(new Date(now).toISOString()).slice(11).split(':').map(Number);
  const resource = useAgendaResource(currentUser.user_id, `calendar:${week}`, () => salesCopilotApi.getCalendar(week), active);
  useEffect(() => { if (active && scrollRef.current) scrollRef.current.scrollTop = 7 * 60; }, [active, week]);
  const data = resource.data;
  const shown = selected && data?.items.find((item) => item.id === selected.id);
  return <div className="agenda-page calendar-page" aria-label="Lịch sự kiện">
    <header className="agenda-page-heading"><div><p className="agenda-eyebrow">LỊCH CÁ NHÂN</p><h1>Lịch sự kiện</h1><p>Công việc và lịch hẹn đã xếp giờ · Giờ Việt Nam.</p></div><button type="button" className="sw-secondary-button" aria-label="Làm mới lịch" disabled={resource.loading} onClick={resource.reload}><RefreshCw size={15} /></button></header>
    <div className="agenda-calendar-toolbar"><div><button type="button" className="sw-secondary-button" aria-label="Tuần trước" onClick={() => setWeek(addDays(week, -7))}><ChevronLeft size={16} /></button><button type="button" className="sw-secondary-button" onClick={() => setWeek(mondayOf())}>Hôm nay</button><button type="button" className="sw-secondary-button" aria-label="Tuần sau" onClick={() => setWeek(addDays(week, 7))}><ChevronRight size={16} /></button></div><strong>{week.split('-').reverse().join('/')} – {addDays(week, 6).split('-').reverse().join('/')}</strong><label>Chọn ngày<input type="date" aria-label="Chọn ngày để xem tuần" value={week} onInput={(event) => { if (event.target.value) setWeek(mondayOf(event.target.value)); }} onChange={(event) => { if (event.target.value) setWeek(mondayOf(event.target.value)); }} /></label></div>
    <div className="agenda-legend"><span><i className="task" />Công việc</span><span><i className="appointment" />Lịch hẹn</span><span><Check size={12} />Hoàn thành</span></div>
    {resource.error && <div className="sw-error-banner" role="alert">{resource.error}<button type="button" className="sw-text-button" onClick={resource.reload}>Thử lại</button></div>}
    <p className="agenda-updated" role="status">{resource.loading ? 'Đang tải lịch…' : data ? `${data.items.length} mục · Cập nhật ${formatDateTime(data.generated_at)}` : 'Chưa tải được lịch.'}{data && !data.items.length && ' · Tuần này chưa có sự kiện được xếp lịch.'}</p>
    <div className="agenda-calendar-scroll" ref={scrollRef}><div className="agenda-calendar-grid">
      <div className="agenda-calendar-corner">UTC+7</div>{weekdays.map((label, index) => { const day = addDays(week, index); return <div className={`agenda-calendar-day-heading ${day === today ? 'is-today' : ''}`} key={day}><span>{label}</span><strong>{day.slice(8)}/{day.slice(5, 7)}</strong></div>; })}
      <div className="agenda-calendar-hours">{Array.from({ length: 24 }, (_, hour) => <span key={hour} style={{ top: hour * 60 }}>{String(hour).padStart(2, '0')}:00</span>)}</div>
      {weekdays.map((_, index) => { const day = addDays(week, index); return <div className={`agenda-calendar-day ${day === today ? 'is-today' : ''}`} key={day} aria-label={day}>
        {layoutDay(data?.items || [], day).map(({ item, top, height, column, columns }) => <button type="button" key={item.id} className={`agenda-calendar-event ${item.item_type} ${item.status === 'completed' ? 'is-completed' : ''}`} style={{ top, height: Math.max(18, height), left: `calc(${column / columns * 100}% + 2px)`, width: `calc(${100 / columns}% - 4px)`, zIndex: height < 30 ? 3 : 2 }} onClick={() => setSelected(item)} title={`${item.title} · ${formatDateTime(item.starts_at)} – ${formatDateTime(item.ends_at)} · ${itemLabel(item)}`}><strong>{item.status === 'completed' && <Check size={11} />}{item.title}</strong><small>{formatDateTime(item.starts_at, false)}–{formatDateTime(item.ends_at, false)}</small><small>{item.customer_name || 'Cá nhân'} · {itemLabel(item)}</small></button>)}
        {day === today && <div className="agenda-now-line" style={{ top: timeNow[0] * 60 + timeNow[1] }} aria-label="Giờ hiện tại" />}
      </div>; })}
    </div></div>
    {shown && <DetailDialog title={itemLabel(shown)} onClose={() => setSelected(null)}><div className="agenda-event-detail"><span className={`agenda-kind ${shown.item_type}`}>{taskState(shown, now)}</span><h3>{shown.title}</h3><p>{formatDateTime(shown.starts_at)} – {formatDateTime(shown.ends_at)}</p><p>{shown.customer_name || 'Cá nhân · Không gắn khách hàng'}</p><p>Ưu tiên: {['high', 'urgent'].includes(shown.priority) ? 'Cao' : shown.priority === 'low' ? 'Thấp' : 'Trung bình'}</p>{shown.description && <p className="agenda-event-note">{shown.description}</p>}<div className="sw-inline-actions"><button type="button" className="sw-primary-button" onClick={() => { setSelected(null); onTask(shown); }}>Xem công việc trên Dashboard</button>{shown.conversation_id && <button type="button" className="sw-secondary-button" onClick={() => { setSelected(null); onCustomer(shown); }}>Mở khách hàng</button>}</div></div></DetailDialog>}
  </div>;
}
