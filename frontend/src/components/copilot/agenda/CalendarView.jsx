import { useEffect, useRef, useState } from 'react';
import {
  Calendar as CalendarIcon,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  MapPin,
  Plus,
  RefreshCw,
  UserRound,
} from 'lucide-react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { DetailDialog } from '../customerWorkspace/WorkspacePrimitives';
import { useWorkspaceClock } from '../customerWorkspace/useCustomerWorkspace';
import {
  addDays,
  dateKey,
  formatDateTime,
  itemLabel,
  layoutDay,
  localInput,
  mondayOf,
  taskState,
} from './agendaData';
import { useAgendaResource } from './agendaResource';

const weekdays = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật'];

function formatShortDate(isoDay) {
  if (!isoDay) return '';
  return isoDay.split('-').reverse().join('/');
}

export function CalendarView({
  currentUser,
  active,
  week,
  onWeekChange: setWeek,
  onCreate,
  onEdit,
  onCustomer,
  onTask,
}) {
  const [selected, setSelected] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [actionError, setActionError] = useState('');
  const scrollRef = useRef(null);
  const now = useWorkspaceClock();
  const today = dateKey(new Date(now).toISOString());
  const timeNow = localInput(new Date(now).toISOString())
    .slice(11)
    .split(':')
    .map(Number);

  const resource = useAgendaResource(
    currentUser.user_id,
    `calendar:${week}`,
    () => salesCopilotApi.getCalendar(week),
    active
  );

  const data = resource.data;
  const items = data?.items || [];

  useEffect(() => {
    if (!active || !scrollRef.current) return;
    if (items.length > 0) {
      const firstHour = Math.min(
        ...items.map((item) => {
          const hm = localInput(item.starts_at).slice(11).split(':').map(Number);
          return Number.isFinite(hm[0]) ? Math.max(0, hm[0] - 1) : 7;
        })
      );
      scrollRef.current.scrollTop = firstHour * 60;
    } else {
      scrollRef.current.scrollTop = 7 * 60;
    }
  }, [active, week, items.length]);

  const shown = selected && items.find((item) => item.id === selected.id);

  async function handleQuickComplete(item) {
    if (!item || busyId) return;
    setBusyId(item.id);
    setActionError('');
    try {
      await salesCopilotApi.updateTaskStatus(item.id, 'completed');
      setSelected(null);
    } catch (err) {
      setActionError(err.message || 'Không thể cập nhật trạng thái.');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="agenda-page calendar-page" aria-label="Lịch sự kiện">
      {/* COMPACT FULL-WIDTH TOP BAR */}
      <header className="agenda-calendar-topbar">
        <div className="agenda-calendar-topbar-left">
          <div className="agenda-calendar-title-block">
            <h1>Lịch sự kiện</h1>
            <span className="agenda-updated" role="status">
              {resource.loading
                ? 'Đang tải lịch…'
                : data
                  ? `${items.length} sự kiện trong tuần · Cập nhật ${formatDateTime(data.generated_at)}`
                  : 'Chưa tải được lịch.'}
            </span>
          </div>

          <div className="agenda-legend">
            <span>
              <i className="task" />
              Công việc
            </span>
            <span>
              <i className="appointment" />
              Lịch hẹn
            </span>
            <span>
              <Check size={12} />
              Hoàn thành
            </span>
          </div>
        </div>

        <div className="agenda-calendar-topbar-center">
          <div className="agenda-calendar-nav-buttons">
            <button
              type="button"
              className="sw-secondary-button"
              aria-label="Tuần trước"
              onClick={() => setWeek(addDays(week, -7))}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              className={`sw-secondary-button ${week === mondayOf() ? 'is-current-week' : ''}`}
              onClick={() => setWeek(mondayOf())}
            >
              Hôm nay
            </button>
            <button
              type="button"
              className="sw-secondary-button"
              aria-label="Tuần sau"
              onClick={() => setWeek(addDays(week, 7))}
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <div className="agenda-calendar-range-badge">
            <CalendarIcon size={14} />
            <strong>
              {formatShortDate(week)} – {formatShortDate(addDays(week, 6))}
            </strong>
          </div>
        </div>

        <div className="agenda-calendar-topbar-right">
          <label className="agenda-date-picker-label">
            <span>Chọn ngày</span>
            <input
              type="date"
              aria-label="Chọn ngày để xem tuần"
              value={week}
              onInput={(event) => {
                if (event.target.value) setWeek(mondayOf(event.target.value));
              }}
              onChange={(event) => {
                if (event.target.value) setWeek(mondayOf(event.target.value));
              }}
            />
          </label>

          {onCreate && (
            <button
              type="button"
              className="sw-primary-button"
              onClick={() => onCreate(data?.customers || [])}
            >
              <Plus size={15} />
              Tạo lịch
            </button>
          )}

          <button
            type="button"
            className="sw-secondary-button"
            aria-label="Làm mới lịch"
            title="Làm mới lịch"
            disabled={resource.loading}
            onClick={resource.reload}
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </header>

      {(resource.error || actionError) && (
        <div className="sw-error-banner" role="alert">
          {resource.error || actionError}
          <button type="button" className="sw-text-button" onClick={resource.reload}>
            Thử lại
          </button>
        </div>
      )}

      {/* FULL-SCREEN 7-DAY CALENDAR GRID */}
      <div className="agenda-calendar-scroll" ref={scrollRef}>
        <div className="agenda-calendar-grid">
          <div className="agenda-calendar-corner">
            <span>Giờ VN</span>
            <small>UTC+7</small>
          </div>

          {weekdays.map((label, index) => {
            const day = addDays(week, index);
            const dayEvents = layoutDay(items, day);
            const eventCount = dayEvents.length;
            const isToday = day === today;
            return (
              <div
                className={`agenda-calendar-day-heading ${isToday ? 'is-today' : ''}`}
                key={day}
              >
                <div className="agenda-day-top-line">
                  <span className="agenda-day-name">{label}</span>
                  {eventCount > 0 && (
                    <span
                      className="agenda-day-count"
                      title={`${eventCount} sự kiện trong ngày ${day.slice(8)}/${day.slice(5, 7)}`}
                      aria-label={`${eventCount} sự kiện`}
                    >
                      {eventCount}
                    </span>
                  )}
                </div>
                <strong className="agenda-day-date">
                  {day.slice(8)}/{day.slice(5, 7)}
                </strong>
              </div>
            );
          })}

          <div className="agenda-calendar-hours">
            {Array.from({ length: 24 }, (_, hour) => (
              <span key={hour} style={{ top: hour * 60 }}>
                {String(hour).padStart(2, '0')}:00
              </span>
            ))}
          </div>

          {weekdays.map((_, index) => {
            const day = addDays(week, index);
            const isToday = day === today;
            const positioned = layoutDay(items, day);
            return (
              <div
                className={`agenda-calendar-day ${isToday ? 'is-today' : ''}`}
                key={day}
                aria-label={day}
              >
                {positioned.map(({ item, top, height, column, columns }) => {
                  const isCompact = height < 44;
                  const timeRange = `${formatDateTime(item.starts_at, false)}–${formatDateTime(item.ends_at, false)}`;
                  return (
                    <button
                      type="button"
                      key={item.id}
                      className={`agenda-calendar-event ${item.item_type} ${item.status === 'completed' ? 'is-completed' : ''} ${isCompact ? 'is-compact' : ''}`}
                      style={{
                        top,
                        height: Math.max(22, height),
                        left: `calc(${(column / columns) * 100}% + 3px)`,
                        width: `calc(${100 / columns}% - 6px)`,
                        zIndex: height < 35 ? 3 : 2,
                      }}
                      onClick={() => setSelected(item)}
                      title={`${item.title} · ${formatDateTime(item.starts_at)} – ${formatDateTime(item.ends_at)} · ${itemLabel(item)}`}
                    >
                      {isCompact ? (
                        <div className="agenda-event-compact-row">
                          <span className="agenda-event-compact-time">
                            {formatDateTime(item.starts_at, false)}
                          </span>
                          <strong>
                            {item.status === 'completed' && <Check size={11} />}
                            {item.title}
                          </strong>
                        </div>
                      ) : (
                        <>
                          <strong>
                            {item.status === 'completed' && <Check size={11} />}
                            {item.title}
                          </strong>
                          <small className="agenda-event-time">{timeRange}</small>
                          {height >= 56 && (
                            <small className="agenda-event-sub">
                              {item.customer_name || 'Cá nhân'} · {itemLabel(item)}
                            </small>
                          )}
                        </>
                      )}
                    </button>
                  );
                })}
                {isToday && (
                  <div
                    className="agenda-now-line"
                    style={{ top: timeNow[0] * 60 + timeNow[1] }}
                    aria-label="Giờ hiện tại"
                  >
                    <span className="agenda-now-badge">
                      {String(timeNow[0]).padStart(2, '0')}:{String(timeNow[1]).padStart(2, '0')}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* EVENT DETAIL DIALOG */}
      {shown && (
        <DetailDialog title={itemLabel(shown)} onClose={() => setSelected(null)}>
          <div className="agenda-event-detail">
            <div className="agenda-event-detail-badges">
              <span className={`agenda-kind ${shown.item_type}`}>{taskState(shown, now)}</span>
              <span className="agenda-priority">
                Ưu tiên:{' '}
                {['high', 'urgent'].includes(shown.priority)
                  ? 'Cao'
                  : shown.priority === 'low'
                    ? 'Thấp'
                    : 'Trung bình'}
              </span>
            </div>
            <h3>{shown.title}</h3>
            <div className="agenda-event-detail-meta">
              <p>
                <Clock3 size={14} /> {formatDateTime(shown.starts_at)} –{' '}
                {formatDateTime(shown.ends_at)}
              </p>
              <p>
                <UserRound size={14} /> {shown.customer_name || 'Cá nhân · Không gắn khách hàng'}
              </p>
              {shown.location && (
                <p>
                  <MapPin size={14} /> {shown.location}
                </p>
              )}
            </div>
            {shown.description && <p className="agenda-event-note">{shown.description}</p>}
            <div className="sw-inline-actions">
              <div>
                {shown.status !== 'completed' && (
                  <button
                    type="button"
                    className="sw-primary-button"
                    disabled={busyId === shown.id}
                    onClick={() => handleQuickComplete(shown)}
                  >
                    <Check size={14} /> Hoàn thành
                  </button>
                )}
                {onEdit && (
                  <button
                    type="button"
                    className="sw-secondary-button"
                    onClick={() => {
                      const target = shown;
                      setSelected(null);
                      onEdit(target);
                    }}
                  >
                    Sửa / Đổi giờ
                  </button>
                )}
                <button
                  type="button"
                  className="sw-secondary-button"
                  onClick={() => {
                    setSelected(null);
                    onTask(shown);
                  }}
                >
                  Xem công việc trên Dashboard
                </button>
                {shown.conversation_id && (
                  <button
                    type="button"
                    className="sw-secondary-button"
                    onClick={() => {
                      setSelected(null);
                      onCustomer(shown);
                    }}
                  >
                    Mở khách hàng
                  </button>
                )}
              </div>
            </div>
          </div>
        </DetailDialog>
      )}
    </div>
  );
}
