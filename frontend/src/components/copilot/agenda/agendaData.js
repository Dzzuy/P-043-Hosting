export const TIMEZONE = 'Asia/Ho_Chi_Minh';
export const filters = { today: 'Hôm nay', upcoming: 'Sắp đến', stale: 'Cần cập nhật', unscheduled: 'Cần xếp lịch', review: 'Cần duyệt', completed: 'Hoàn thành' };
export const itemLabel = (task) => task.item_type === 'appointment' ? 'Lịch hẹn' : 'Công việc';
export function localInput(value) {
  if (!value) return '';
  const parsed = new Date(/T.*(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`);
  if (!Number.isFinite(parsed.getTime())) return '';
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(parsed).map(({ type, value: part }) => [type, part]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}
export const toUTC = (value) => value ? new Date(`${value}:00+07:00`).toISOString() : null;
export const dateKey = (value = new Date().toISOString()) => localInput(value).slice(0, 10);
export function addDays(day, count) {
  const value = new Date(`${day}T00:00:00Z`); value.setUTCDate(value.getUTCDate() + count); return value.toISOString().slice(0, 10);
}
export function mondayOf(day = dateKey()) {
  const dow = new Date(`${day}T00:00:00Z`).getUTCDay(); return addDays(day, -((dow + 6) % 7));
}
export function formatDateTime(value, date = true) {
  if (!value) return 'Cần xếp lịch';
  return new Intl.DateTimeFormat('vi-VN', { timeZone: TIMEZONE, hour: '2-digit', minute: '2-digit', ...(date ? { day: '2-digit', month: '2-digit' } : {}) }).format(new Date(value));
}
export function defaultTaskWindow(kind = 'task', offsetMinutes = 0) {
  const durationMinutes = kind === 'appointment' ? 60 : 30;
  const now = new Date();
  const slotMs = 30 * 60 * 1000;
  const roundedStartMs = Math.ceil((now.getTime() + 5 * 60 * 1000) / slotMs) * slotMs + offsetMinutes * 60 * 1000;
  const startIso = new Date(roundedStartMs).toISOString();
  const endIso = new Date(roundedStartMs + durationMinutes * 60 * 1000).toISOString();
  return { start: localInput(startIso), end: localInput(endIso) };
}
export function waitingDuration(value, now = Date.now()) {
  const since = new Date(value).getTime();
  if (!value || !Number.isFinite(since)) return 'Đang chờ phản hồi';
  const minutes = Math.max(0, Math.floor((now - since) / 60000));
  if (minutes < 1) return 'Chờ dưới 1 phút';
  if (minutes < 60) return `Chờ ${minutes} phút`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Chờ ${hours} giờ ${minutes % 60} phút`;
  return `Chờ ${Math.floor(hours / 24)} ngày ${hours % 24} giờ`;
}
export function taskState(task, now = Date.now()) {
  if (task.status === 'completed') return 'Hoàn thành';
  if (task.status === 'cancelled') return 'Đã hủy';
  if (task.status === 'needs_review') return 'Cần duyệt';
  if (!task.starts_at || !task.ends_at) return 'Cần xếp lịch';
  if (new Date(task.ends_at).getTime() <= now) return 'Cần cập nhật trạng thái';
  return new Date(task.starts_at).getTime() <= now ? 'Đang diễn ra' : 'Sắp diễn ra';
}

/** Clip across midnight, then assign columns per connected group of overlapping intervals. */
export function layoutDay(items, day) {
  const start = new Date(`${day}T00:00:00+07:00`).getTime(); const end = start + 86400000;
  const segments = items.filter((item) => new Date(item.starts_at).getTime() < end && new Date(item.ends_at).getTime() > start).map((item) => ({ item, start: Math.max(start, new Date(item.starts_at).getTime()), end: Math.min(end, new Date(item.ends_at).getTime()) })).sort((a, b) => a.start - b.start || b.end - a.end || a.item.id.localeCompare(b.item.id));
  let group = []; let groupEnd = 0;
  function flush() {
    const columns = [];
    for (const segment of group) { let col = columns.findIndex((until) => until <= segment.start); if (col === -1) col = columns.length; columns[col] = segment.end; segment.column = col; }
    for (const segment of group) segment.columns = columns.length;
  }
  for (const segment of segments) {
    if (group.length && segment.start >= groupEnd) { flush(); group = []; groupEnd = 0; }
    group.push(segment); groupEnd = Math.max(groupEnd, segment.end);
  }
  flush();
  return segments.map((segment) => ({ ...segment, top: (segment.start - start) / 60000, height: (segment.end - segment.start) / 60000 }));
}
