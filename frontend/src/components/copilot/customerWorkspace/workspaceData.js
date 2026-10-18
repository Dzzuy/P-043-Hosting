import { customerIntelligence } from './customerIntelligence.js';

const stageLabels = {
  new: ['Mới liên hệ', 'gray'], discovery: ['Tìm hiểu nhu cầu', 'blue'], qualified: ['Đang tư vấn', 'blue'],
  considering: ['Đang cân nhắc', 'amber'], negotiating: ['Đang đàm phán', 'purple'],
  deposit_process: ['Chuẩn bị đặt cọc', 'amber'], won: ['Đã ký hợp đồng', 'green'], lost: ['Ngừng chăm sóc', 'gray'],
};
export const leadStages = Object.entries(stageLabels).map(([id, [label]]) => ({ id, label }));

export function timestamp(value) {
  if (!value) return NaN;
  // Older API records use naive UTC timestamps.
  const normalized = /^\d{4}-\d{2}-\d{2}T/.test(value) && !/(Z|[+-]\d{2}:\d{2})$/i.test(value) ? `${value}Z` : value;
  return new Date(normalized).getTime();
}

export function displayDateTime(value) {
  const time = timestamp(value);
  return Number.isFinite(time) ? new Date(time).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric' }) : 'Chưa cập nhật';
}

export function taskCounts(tasks, now = Date.now()) {
  const pending = tasks.filter((task) => !task.completed && !['completed', 'cancelled'].includes(task.status));
  return { pending: pending.length, overdue: pending.filter((task) => task.status !== 'needs_review' && timestamp(task.ends_at) <= now).length };
}

export function appendDraft(value, draft) {
  return value.trim() ? `${value.trimEnd()}\n\n${draft}` : draft;
}
const palette = ['blue', 'purple', 'teal', 'pink', 'peach', 'lavender'];

export function normalizeSearch(value) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();
}

export function filterCustomers(customers, query, filter) {
  const search = normalizeSearch(query.trim());
  return customers.filter((customer) => {
    const matchesStatus = filter === 'attention' ? customer.attention : filter === 'caring' ? !['new', 'won', 'lost'].includes(customer.stageId) : true;
    return matchesStatus && (!search || normalizeSearch(`${customer.name} ${customer.model} ${customer.phone}`).includes(search));
  });
}

export function displayTime(value) {
  if (!value) return '';
  const date = new Date(timestamp(value));
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function localDate(value) {
  const date = new Date(timestamp(value));
  if (!value || Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function toWorkspaceMessage(message) {
  return { id: message.id, seq: message.seq, role: message.sender_role, content: message.content, time: displayTime(message.sent_at), date: localDate(message.sent_at), sentAt: message.sent_at };
}

export function toWorkspaceTask(task) {
  return { ...task, completed: task.status === 'completed', ownerId: task.owner_sales_id, manual: task.task_type === 'manual_follow_up', sourceMessageIds: task.source_message_ids || [] };
}

export function taskGroups(tasks, now = Date.now()) {
  return [
    ['live', 'Đang diễn ra', (task) => !task.completed && task.status !== 'needs_review' && timestamp(task.starts_at) <= now && timestamp(task.ends_at) > now],
    ['upcoming', 'Sắp diễn ra', (task) => !task.completed && task.status !== 'needs_review' && timestamp(task.starts_at) > now],
    ['overdue', 'Cần cập nhật trạng thái', (task) => !task.completed && task.status !== 'needs_review' && timestamp(task.ends_at) <= now],
    ['unscheduled', 'Cần xếp lịch', (task) => !task.completed && task.status !== 'needs_review' && !Number.isFinite(timestamp(task.starts_at))],
    ['review', 'Cần duyệt', (task) => task.status === 'needs_review'],
    ['completed', 'Hoàn thành', (task) => task.completed],
  ].map(([id, label, matches]) => ({ id, label, tasks: tasks.filter((task) => task.status !== 'cancelled' && matches(task)) }));
}

export function mergeMessages(existing, incoming) {
  return [...new Map([...existing, ...incoming].map((message) => [message.id, message])).values()].sort((a, b) => a.seq - b.seq);
}

export function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '';
  return `${Number(value).toLocaleString('vi-VN')} ₫`;
}

/** Adapt API state without substituting synthetic messages or inferred financial facts. */
export function toWorkspaceCustomer(item, detail, savedDraft, index = 0, now = Date.now()) {
  const profile = detail?.profile || {};
  const name = detail?.customer_name || item.customer_name || 'Khách hàng';
  const models = Array.isArray(profile.interested_models) ? profile.interested_models : item.interested_models || [];
  const model = models.join(', ') || 'Chưa xác định xe';
  const stageId = (detail ? detail.lead_status?.stage : item.lead_stage) ?? 'needs_confirmation';
  const [stage, tone] = stageLabels[stageId] || ['Cần xác nhận giai đoạn', 'gray'];
  const messages = (detail?.messages || []).map(toWorkspaceMessage);
  // Paginated sources are validated by the owned-conversation messages endpoint when opened.
  const validSources = new Set(messages.map((message) => message.id));
  const sourceAllowed = (id) => id && (detail?.message_total !== undefined || validSources.has(id));
  const updatedAt = detail?.memory?.updated_at || detail?.last_analyzed_at || item.last_analyzed_at;
  const primaryModel = models[0]?.match(/VF\s*([3-9])/i)?.[1];
  const tasks = (detail?.tasks || []).filter((task) => task.status !== 'cancelled').map(toWorkspaceTask);
  const throughSeq = detail?.memory?.analyzed_through_seq;
  const lastSeq = detail?.last_message_seq ?? item.last_message_seq ?? messages.at(-1)?.seq ?? 0;
  const pendingAnalysis = detail
    ? (Number.isInteger(throughSeq)
      ? Math.max(0, lastSeq - throughSeq)
      : updatedAt ? messages.filter((message) => timestamp(message.sentAt) > timestamp(updatedAt)).length : detail?.message_total ?? messages.length)
    : (item.pending_analysis_count ?? (item.analysis_version ? 0 : item.message_total ?? 0));
  const draftSeq = savedDraft?.based_on_message_seq;
  const draftStale = Number.isInteger(draftSeq)
    ? lastSeq > draftSeq
    : Boolean(savedDraft?.generated_at && messages.some((message) => timestamp(message.sentAt) > timestamp(savedDraft.generated_at)));
  const timeline = detail?.memory?.stage ? (detail.milestones || []).map((m) => ({
    title: m.action, event_type: m.event_type, occurred_at: m.occurred_at || m.created_at,
    source_message_id: m.evidence?.[0]?.message_id || m.source_message_ids?.[0],
  })) : (detail?.memory?.timeline || []);
  const events = timeline.map((event, eventIndex) => ({
    id: `${item.conversation_id}-event-${eventIndex}`, time: event.occurred_at || 'Chưa rõ thời gian', text: event.description || event.title,
    type: event.event_type || 'general',
    tone: ['amber', 'blue', 'green', 'gray'][eventIndex % 4], sourceMessageId: sourceAllowed(event.source_message_id) ? event.source_message_id : null,
  }));
  return {
    id: item.conversation_id, customerId: item.customer_id, name,
    initials: name.split(/\s+/).filter(Boolean).at(-1)?.charAt(0) || 'K', color: palette[index % palette.length],
    model, primaryModel, image: primaryModel ? `/vehicles/vf-${primaryModel}.jpg` : null, segment: 'Thông tin sản phẩm',
    budget: profile.budget_notes || formatMoney(profile.budget_vnd) || item.budget_notes || formatMoney(item.budget_vnd) || 'Chưa xác định',
    deposit: formatMoney(profile.down_payment_vnd), payment: ({ cash: 'Trả thẳng', installment: 'Trả góp', mixed: 'Kết hợp' })[profile.payment_method] || profile.payment_method || 'Chưa xác định',
    location: detail?.customer_location || item.location || 'Chưa cập nhật', phone: item.phone || 'Chưa cập nhật',
    stageId, stage, tone,
    attention: (detail ? messages.at(-1)?.role === 'customer' || tasks.some((task) => !task.completed && task.status !== 'needs_review' && ['high', 'urgent'].includes(task.priority) && timestamp(task.ends_at) <= now) : item.last_sender_role === 'customer' || item.important_overdue_count > 0),
    attentionReason: (detail ? messages.at(-1)?.role : item.last_sender_role) === 'customer' ? 'Khách đang chờ phản hồi' : 'Công việc quan trọng cần cập nhật trạng thái',
    preview: item.last_message || 'Chưa có tin nhắn', time: displayTime(updatedAt), lastMessageTime: displayTime(item.last_message_at),
    messages, messageTotal: detail?.message_total ?? item.message_total ?? messages.length, nextBeforeSeq: detail?.next_before_seq, tasks, profile, analysisVersion: detail?.analysis_version ?? item.analysis_version ?? 0,
    summary: detail?.memory?.quick_summary || '', draft: savedDraft?.text || '',
    intelligence: customerIntelligence(detail?.memory, profile, sourceAllowed),
    usage: profile.usage_purpose || 'Chưa rõ nhu cầu', updatedAt, pendingAnalysis,
    pendingItems: detail?.memory?.pending_items || [], promises: detail?.memory?.key_promises || [],
    consultationProgress: {
      summary: detail?.memory?.detailed_summary || '',
      consultedTopics: events.filter((event) => event.type === 'consulted'),
      // A sales reply or a completed task alone does not prove the customer's issue is resolved.
      resolvedIssues: events.filter((event) => event.type === 'resolved' && event.sourceMessageId),
      openQuestions: [...new Set([...(detail?.memory?.pending_items || []), ...(profile.unresolved_questions || [])])],
    },
    concerns: profile.objections_and_concerns || [],
    facts: (profile.facts || []).map((fact) => ({ ...fact, source_message_ids: (fact.source_message_ids || []).filter(sourceAllowed) })),
    lead: detail?.lead_status || {},
    draftId: savedDraft?.draft_id, draftGeneratedAt: savedDraft?.generated_at,
    draftStale, draftContext: savedDraft?.context_trigger || '', draftSources: savedDraft?.sources || [],
    draftContextKnown: Number.isInteger(draftSeq),
    events,
    documents: [], loaded: Boolean(detail),
  };
}
