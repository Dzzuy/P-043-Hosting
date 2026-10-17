import test from 'node:test';
import assert from 'node:assert/strict';
import { dateKey, localInput, toUTC, mondayOf, addDays, layoutDay, taskState, waitingDuration } from '../src/components/copilot/agenda/agendaData.js';

test('Vietnam scheduling is independent of the browser timezone and starts the week on Monday', () => {
  assert.equal(localInput('2026-10-15T17:30:00Z'), '2026-10-16T00:30');
  assert.equal(toUTC('2026-10-16T00:30'), '2026-10-15T17:30:00.000Z');
  assert.equal(dateKey('2026-10-18T17:00:00Z'), '2026-10-19');
  assert.equal(mondayOf('2026-10-18'), '2026-10-12');
  assert.equal(mondayOf('2026-10-19'), '2026-10-19');
  assert.equal(addDays('2026-12-28', 7), '2027-01-04');
});

test('calendar clips cross-midnight events and excludes the next-day boundary', () => {
  const items = [
    { id: 'night', starts_at: '2026-10-16T23:30:00+07:00', ends_at: '2026-10-17T01:00:00+07:00' },
    { id: 'next', starts_at: '2026-10-17T00:00:00+07:00', ends_at: '2026-10-17T02:00:00+07:00' },
  ];
  const friday = layoutDay(items, '2026-10-16');
  assert.equal(friday.length, 1); assert.equal(friday[0].top, 1410); assert.equal(friday[0].height, 30);
  const saturday = layoutDay(items, '2026-10-17');
  assert.equal(saturday.length, 2); assert.equal(saturday.find((item) => item.item.id === 'night').height, 60);
  assert.ok(saturday.every((item) => item.columns === 2));
});

test('overlapping events share columns; adjacent appointments reuse the full width', () => {
  const event = (id, start, end) => ({ id, starts_at: `2026-10-16T${start}:00+07:00`, ends_at: `2026-10-16T${end}:00+07:00` });
  const items = layoutDay([event('a', '08:00', '10:00'), event('b', '08:30', '09:00'), event('c', '09:00', '09:30'), event('d', '10:00', '11:00')], '2026-10-16');
  assert.equal(items.find((item) => item.item.id === 'a').columns, 2);
  assert.equal(items.find((item) => item.item.id === 'b').column, items.find((item) => item.item.id === 'c').column);
  assert.equal(items.find((item) => item.item.id === 'd').columns, 1);
});

test('legacy and proposed tasks remain unscheduled; expired events request a status update', () => {
  const now = Date.parse('2026-10-16T02:00:00Z');
  assert.equal(taskState({ due_at: '2026-10-10T00:00:00Z' }, now), 'Cần xếp lịch');
  assert.equal(taskState({ status: 'needs_review' }, now), 'Cần duyệt');
  assert.equal(taskState({ starts_at: '2026-10-16T01:00:00Z', ends_at: '2026-10-16T02:00:00Z' }, now), 'Cần cập nhật trạng thái');
  assert.equal(taskState({ starts_at: '2026-10-16T02:00:00Z', ends_at: '2026-10-16T03:00:00Z' }, now), 'Đang diễn ra');
});

test('waiting time stays readable across minute, hour and day boundaries', () => {
  const now = Date.parse('2026-10-16T02:00:00Z');
  assert.equal(waitingDuration('2026-10-16T01:59:30Z', now), 'Chờ dưới 1 phút');
  assert.equal(waitingDuration('2026-10-16T01:55:00Z', now), 'Chờ 5 phút');
  assert.equal(waitingDuration('2026-10-16T00:55:00Z', now), 'Chờ 1 giờ 5 phút');
  assert.equal(waitingDuration('2026-10-15T00:00:00Z', now), 'Chờ 1 ngày 2 giờ');
});
