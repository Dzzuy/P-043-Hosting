import test from 'node:test';
import assert from 'node:assert/strict';
import { appendDraft, filterCustomers, headerFacts, mergeMessages, taskCounts, taskGroups, timestamp, toWorkspaceCustomer } from '../src/components/copilot/customerWorkspace/workspaceData.js';
import { readWorkspaceState } from '../src/components/copilot/customerWorkspace/workspaceStorage.js';

const item = { conversation_id: 'conv-1', customer_id: 'customer-1', customer_name: 'Anh Tuấn', phone: '0900000001', lead_stage: 'considering', interested_models: ['VF 6'], pending_tasks_count: 2 };

test('concise intelligence uses latest topic, deduplicates and preserves paginated evidence', () => {
  const customer = toWorkspaceCustomer(item, { message_total: 80, memory: {
    quick_summary: 'Khách cân nhắc VF 6.', customer_intelligence: {
      key_points: [
        { topic: 'Tài chính', answer: 'Bản cũ', status: 'answered' },
        { topic: 'TÀI CHÍNH.', question: 'Khách hỏi lãi vay', answer: 'Chưa có mức lãi xác nhận', status: 'open', source_message_ids: ['m1'] },
        { topic: 'Lựa chọn', answer: 'Chọn VF 6', status: 'answered' },
      ],
      outcomes: [{ text: 'Chọn VF 6', source_message_ids: ['m2'] }, { text: 'Chọn VF 6.', source_message_ids: ['m2'] }],
      commitments: [{ actor: 'Sales', action: 'Gửi bảng tính', time: '', source_message_ids: ['m3'] }],
    },
  } });
  assert.equal(customer.intelligence.keyPoints.length, 1);
  assert.equal(customer.intelligence.keyPoints[0].status, 'open');
  assert.deepEqual(customer.intelligence.keyPoints[0].sourceMessageIds, ['m1']);
  assert.equal(customer.intelligence.outcomes.length, 1);
  assert.equal(customer.intelligence.commitments[0].text, 'Sales — Gửi bảng tính');
});

test('legacy intelligence collapses duplicate open issues and leaves optional sections empty', () => {
  const customer = toWorkspaceCustomer(item, { profile: { unresolved_questions: ['Điểm sạc.'] },
    memory: { quick_summary: 'Tổng quan cũ', detailed_summary: 'Không lặp', pending_items: [' điểm sạc '] } });
  assert.equal(customer.intelligence.recap, 'Tổng quan cũ');
  assert.equal(customer.intelligence.keyPoints.length, 1);
  assert.deepEqual(customer.intelligence.outcomes, []);
  assert.deepEqual(customer.intelligence.commitments, []);
});

test('a legacy promise duplicated in key_promises keeps its message evidence', () => {
  const customer = toWorkspaceCustomer(item, { message_total: 80, memory: {
    key_promises: ['Sales gửi báo giá.'], timeline: [
      { event_type: 'promise', description: 'Sales gửi báo giá', source_message_id: 'old-message' },
    ],
  } });
  assert.equal(customer.intelligence.commitments.length, 1);
  assert.deepEqual(customer.intelligence.commitments[0].sourceMessageIds, ['old-message']);
});

test('customer intelligence keeps profile and consultation progress together without inventing resolution', () => {
  const customer = toWorkspaceCustomer(item, {
    messages: [{ id: 'customer-confirmation', sender_role: 'customer' }],
    profile: { budget_vnd: 700000000, unresolved_questions: ['Điểm sạc', 'Thời gian giao xe'] },
    memory: { detailed_summary: 'Đã tư vấn tài chính, còn chờ lịch giao.', pending_items: ['Điểm sạc'], timeline: [
      { title: 'Đã tư vấn trả góp', event_type: 'consulted' },
      { title: 'Đã giải quyết', event_type: 'resolved', source_message_id: 'customer-confirmation' },
      { title: 'Không có bằng chứng', event_type: 'resolved', source_message_id: 'outside-conversation' },
      { title: 'Đã trả lời', event_type: 'general' },
    ] }, tasks: [{ id: 'done', status: 'completed' }],
  });
  assert.equal(customer.budget, '700.000.000 ₫');
  assert.equal(customer.consultationProgress.summary, 'Đã tư vấn tài chính, còn chờ lịch giao.');
  assert.deepEqual(customer.consultationProgress.openQuestions, ['Điểm sạc', 'Thời gian giao xe']);
  assert.equal(customer.consultationProgress.consultedTopics.length, 1);
  assert.equal(customer.consultationProgress.resolvedIssues.length, 1);
  const legacy = toWorkspaceCustomer(item, { memory: { detailed_summary: 'Diễn biến đã lưu từ trước' } });
  assert.equal(legacy.consultationProgress.summary, 'Diễn biến đã lưu từ trước');
  assert.deepEqual(legacy.consultationProgress.resolvedIssues, []);
});

test('missing database fields stay unknown instead of becoming sample facts', () => {
  const customer = toWorkspaceCustomer(item);
  assert.equal(customer.name, 'Anh Tuấn');
  assert.equal(customer.budget, 'Chưa xác định');
  assert.equal(customer.payment, 'Chưa xác định');
  assert.deepEqual(customer.messages, []);
  assert.equal(customer.summary, '');
  assert.equal(customer.loaded, false);
});

test('timeline links only reference messages present in this conversation', () => {
  const customer = toWorkspaceCustomer(item, { id: 'conv-1', messages: [{ id: 'message-1', sender_role: 'customer', content: 'Ngân sách 700 triệu', sent_at: '2026-10-16T08:00:00+07:00' }], profile: { budget_vnd: 700000000, payment_method: 'installment' }, memory: { timeline: [{ title: 'Ngân sách', source_message_id: 'message-1' }, { title: 'Nguồn không còn tồn tại', source_message_id: 'other-customer-message' }] } });
  assert.equal(customer.events[0].sourceMessageId, 'message-1');
  assert.equal(customer.events[1].sourceMessageId, null);
  assert.equal(customer.payment, 'Trả góp');
  assert.equal(customer.messages[0].content, 'Ngân sách 700 triệu');
});

test('attention requires a customer awaiting reply or an important overdue task, independently of lead score', () => {
  const noTasks = toWorkspaceCustomer({ ...item, lead_score: 100, pending_tasks_count: 0 });
  const withTasks = toWorkspaceCustomer({ ...item, conversation_id: 'conv-2', lead_score: 0, important_overdue_count: 1 });
  assert.deepEqual(filterCustomers([noTasks, withTasks], '', 'attention').map((customer) => customer.id), ['conv-2']);
  assert.equal(filterCustomers([withTasks], 'tuan vf 6', 'all').length, 1);
});

test('pagination keeps old source IDs, computes freshness from the server cursor and merges without duplicates', () => {
  const customer = toWorkspaceCustomer(item, { message_total: 80, last_message_seq: 80, next_before_seq: 51,
    messages: [{ id: 'm80', seq: 80 }], profile: { facts: [{ field: 'usage_purpose', source_message_ids: ['m1'] }] },
    memory: { analyzed_through_seq: 60, timeline: [{ source_message_id: 'm1' }] },
  }, { based_on_message_seq: 75 });
  assert.equal(customer.pendingAnalysis, 20); assert.equal(customer.messageTotal, 80); assert.equal(customer.draftStale, true);
  assert.equal(customer.events[0].sourceMessageId, 'm1'); assert.deepEqual(customer.facts[0].source_message_ids, ['m1']);
  assert.deepEqual(mergeMessages([{ id: 'm2', seq: 2 }], [{ id: 'm1', seq: 1 }, { id: 'm2', seq: 2 }]).map((message) => message.id), ['m1', 'm2']);
});

test('task grouping uses execution intervals and retains legacy unscheduled items', () => {
  const tasks = [{ id: 'o', starts_at: '2020-01-01', ends_at: '2020-01-02' }, { id: 'u', starts_at: '2090-01-01', ends_at: '2090-01-02' }, { id: 'n' }, { id: 'c', completed: true, ends_at: '2020-01-01' }];
  assert.deepEqual(taskGroups(tasks).map((group) => group.tasks.map((task) => task.id)), [[], ['u'], ['o'], ['n'], [], ['c']]);
  assert.deepEqual(headerFacts({ model: 'VF 3', deposit: '150.000.000 ₫', payment: 'Trả góp', facts: [{ field: 'down_payment_vnd', verification_status: 'inferred' }] }), ['VF 3', 'Trả góp']);
});

test('local drafts and favorites are isolated by owner and survive serialized storage; corrupt data is harmless', () => {
  const data = new Map([['sales-workspace:v1:sales-a', JSON.stringify({ drafts: { c1: 'Dạ anh…' }, starred: { c1: true } })]]);
  const storage = { getItem: (key) => data.get(key) };
  assert.equal(readWorkspaceState(storage, 'sales-a').drafts.c1, 'Dạ anh…');
  assert.equal(readWorkspaceState(storage, 'sales-a').starred.c1, true);
  assert.deepEqual(readWorkspaceState(storage, 'sales-b'), { drafts: {}, starred: {} });
  data.set('sales-workspace:v1:sales-a', '{bad JSON');
  assert.deepEqual(readWorkspaceState(storage, 'sales-a').drafts, {});
});

test('analysis and draft freshness use message sequence even if a message arrived before generation finished', () => {
  const customer = toWorkspaceCustomer(item, {
    messages: [
      { id: 'm1', seq: 1, sent_at: '2026-10-16T08:00:00Z' },
      { id: 'm2', seq: 2, sent_at: '2026-10-16T08:00:01Z' },
    ],
    memory: { updated_at: '2026-10-16T08:00:05Z', analyzed_through_seq: 1 },
  }, { text: 'Bản nháp', based_on_message_seq: 1, generated_at: '2026-10-16T08:00:05Z' });
  assert.equal(customer.pendingAnalysis, 1);
  assert.equal(customer.draftStale, true);
  assert.equal(customer.draftContextKnown, true);
});

test('legacy timestamps are UTC and cached drafts become stale after a later message', () => {
  assert.equal(timestamp('2026-10-16T08:00:00'), timestamp('2026-10-16T15:00:00+07:00'));
  const customer = toWorkspaceCustomer(item, {
    messages: [{ id: 'm1', seq: 3, sent_at: '2026-10-16T08:01:00Z' }],
    memory: { updated_at: '2026-10-16T08:00:00' },
  }, { text: 'Bản nháp cũ', generated_at: '2026-10-16T08:00:00' });
  assert.equal(customer.pendingAnalysis, 1);
  assert.equal(customer.draftStale, true);
  assert.equal(customer.draftContextKnown, false);
});

test('profile sources cannot jump into another customer conversation', () => {
  const customer = toWorkspaceCustomer(item, { profile: { facts: [{ field: 'budget_vnd', source_message_ids: ['mine', 'other'] }] }, messages: [{ id: 'mine' }] });
  assert.deepEqual(customer.facts[0].source_message_ids, ['mine']);
});

test('inserting a reply keeps the sales draft and task attention excludes completed tasks', () => {
  assert.equal(appendDraft('Đang soạn...', 'Gợi ý mới'), 'Đang soạn...\n\nGợi ý mới');
  assert.equal(appendDraft('   ', 'Gợi ý mới'), 'Gợi ý mới');
  assert.deepEqual(taskCounts([
    { status: 'pending', ends_at: '2026-10-15T08:00:00Z' },
    { status: 'completed', completed: true, ends_at: '2026-10-15T08:00:00Z' },
    { status: 'cancelled', ends_at: '2026-10-15T08:00:00Z' },
    { status: 'pending', ends_at: '' },
  ], timestamp('2026-10-16T08:00:00Z')), { pending: 2, overdue: 1 });
});
