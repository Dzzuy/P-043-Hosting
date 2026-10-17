import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { mergeMessages, toWorkspaceCustomer } from './workspaceData';
import { useSalesLookup } from './useSalesLookup';
import { replySuggestionsAvailable } from './workspaceFeatures';
import { CHANGE_EVENT } from '../agenda/agendaResource';

export function useWorkspaceClock() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 60000); return () => clearInterval(timer); }, []);
  return now;
}

/** Conversation data stays keyed by ID; responses never replace a different customer's workspace. */
export function useCustomerWorkspace(currentUser, active = true) {
  const now = useWorkspaceClock();
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [details, setDetails] = useState({});
  const [savedDrafts, setSavedDrafts] = useState({});
  const [listStatus, setListStatus] = useState('loading');
  const [listError, setListError] = useState('');
  const [detailErrors, setDetailErrors] = useState({});
  const [pending, setPending] = useState({});
  const [sendingIds, setSendingIds] = useState({});
  const [taskBusy, setTaskBusy] = useState({});
  const [analysisIds, setAnalysisIds] = useState({});
  const [draftBusyIds, setDraftBusyIds] = useState({});
  const [stageBusyIds, setStageBusyIds] = useState({});
  const [pageBusy, setPageBusy] = useState({});
  const [analysisChanges, setAnalysisChanges] = useState({});
  const lookup = useSalesLookup(currentUser?.user_id);
  const [preferences, setPreferences] = useState(null);
  const [preferenceBusy, setPreferenceBusy] = useState(false);
  const requests = useRef(new Map());
  const mutations = useRef(new Set());
  const detailCache = useRef({});
  const detailFetchedAt = useRef({});
  const draftCache = useRef(new Set());

  const loadList = useCallback(() => {
    if (requests.current.has('list')) return requests.current.get('list');
    setListStatus('loading');
    setListError('');
    const request = salesCopilotApi.getConversations().then((data) => {
      setItems(data || []);
      setSelectedId((previous) => previous && data.some((item) => item.conversation_id === previous) ? previous : data[0]?.conversation_id || null);
      setListStatus('ready');
    }).catch((error) => { setListStatus('error'); setListError(error.message); }).finally(() => requests.current.delete('list'));
    requests.current.set('list', request);
    return request;
  }, []);

  const loadDetails = useCallback((id, force = false) => {
    if (!id) return Promise.resolve();
    if (requests.current.has(`detail:${id}`)) return requests.current.get(`detail:${id}`);
    if (!force && detailCache.current[id] && Date.now() - detailFetchedAt.current[id] < 30000) return Promise.resolve(detailCache.current[id]);
    setPending((previous) => ({ ...previous, [id]: true }));
    setDetailErrors((previous) => ({ ...previous, [id]: '' }));
    const request = salesCopilotApi.getConversationDetails(id).then((data) => {
      detailCache.current[id] = data;
      detailFetchedAt.current[id] = Date.now();
      setDetails((previous) => ({ ...previous, [id]: data }));
      return data;
    }).catch((error) => { setDetailErrors((previous) => ({ ...previous, [id]: error.message })); }).finally(() => {
      setPending((previous) => ({ ...previous, [id]: false }));
      requests.current.delete(`detail:${id}`);
    });
    requests.current.set(`detail:${id}`, request);
    return request;
  }, []);

  useEffect(() => { if (active) void loadList(); }, [active, loadList]);
  useEffect(() => { if (active) void loadDetails(selectedId); }, [active, selectedId, loadDetails]);
  useEffect(() => {
    const changed = () => { detailFetchedAt.current = {}; };
    window.addEventListener(CHANGE_EVENT, changed);
    return () => window.removeEventListener(CHANGE_EVENT, changed);
  }, []);
  useEffect(() => {
    if (!replySuggestionsAvailable) return;
    if (!requests.current.has('preferences')) requests.current.set('preferences', salesCopilotApi.getPreferences());
    let cancelled = false;
    requests.current.get('preferences').then((data) => { if (!cancelled) setPreferences(data); }).catch(() => { if (!cancelled) setPreferences({ advisor_id: currentUser?.user_id, nba_enabled: false, draft_enabled: false }); });
    return () => { cancelled = true; };
  }, [currentUser?.user_id]);
  const loadSavedDraft = useCallback((id, force = false) => {
    if (!id || (!force && draftCache.current.has(id))) return Promise.resolve();
    if (requests.current.has(`draft:${id}`)) return requests.current.get(`draft:${id}`);
    const request = salesCopilotApi.getSavedDraft(id).then((data) => {
      draftCache.current.add(id);
      setSavedDrafts((previous) => ({ ...previous, [id]: data }));
    }).catch(() => {}).finally(() => requests.current.delete(`draft:${id}`));
    requests.current.set(`draft:${id}`, request);
    return request;
  }, []);
  useEffect(() => { if (replySuggestionsAvailable && preferences?.draft_enabled) void loadSavedDraft(selectedId); }, [selectedId, loadSavedDraft, preferences?.draft_enabled]);

  function updateDetail(id, update) {
    const previous = detailCache.current[id];
    if (!previous) return;
    const next = update(previous);
    detailCache.current[id] = next;
    setDetails((all) => ({ ...all, [id]: next }));
  }

  async function sendMessage(id, content) {
    if (mutations.current.has(`send:${id}`)) return null;
    mutations.current.add(`send:${id}`);
    setSendingIds((previous) => ({ ...previous, [id]: true }));
    try {
      const message = await salesCopilotApi.sendMessage(id, content);
      updateDetail(id, (detail) => ({ ...detail, message_total: detail.message_total + (detail.messages.some((item) => item.id === message.id) ? 0 : 1), last_message_seq: message.seq, messages: mergeMessages(detail.messages, [message]) }));
      setItems((previous) => previous.map((item) => item.conversation_id === id ? { ...item, last_message: message.content, last_message_at: message.sent_at, last_sender_role: 'sales' } : item));
      return message;
    } finally { mutations.current.delete(`send:${id}`); setSendingIds((previous) => ({ ...previous, [id]: false })); }
  }

  async function toggleTask(id, task) {
    if (mutations.current.has(task.id)) return;
    mutations.current.add(task.id);
    setTaskBusy((previous) => ({ ...previous, [task.id]: true }));
    const status = task.completed ? 'pending' : 'completed';
    try {
      await salesCopilotApi.updateTaskStatus(task.id, status);
      updateDetail(id, (detail) => ({ ...detail, tasks: detail.tasks.map((item) => item.id === task.id ? { ...item, status } : item) }));
    } finally { mutations.current.delete(task.id); setTaskBusy((previous) => ({ ...previous, [task.id]: false })); }
  }

  async function createTask(id, task) {
    const { customer_id: customerId, ...values } = task;
    const created = customerId === null ? await salesCopilotApi.createPersonalTask(values) : await salesCopilotApi.createTask(id, values);
    if (created.customer_id) updateDetail(id, (detail) => ({ ...detail, tasks: [created, ...detail.tasks] }));
    return created;
  }

  async function loadMessages(id, options = {}) {
    const key = `page:${id}:${options.sourceMessageId || options.beforeSeq}`;
    if (requests.current.has(key)) return requests.current.get(key);
    setPageBusy((previous) => ({ ...previous, [id]: true }));
    const request = salesCopilotApi.getMessagePage(id, options).then((page) => {
      updateDetail(id, (detail) => {
        const messages = mergeMessages(detail.messages, page.messages);
        return { ...detail, messages, next_before_seq: messages[0]?.seq > 1 ? messages[0].seq : null };
      });
      return page;
    }).finally(() => { requests.current.delete(key); setPageBusy((previous) => ({ ...previous, [id]: false })); });
    requests.current.set(key, request);
    return request;
  }

  async function ensureSource(id, sourceMessageId) {
    if (!detailCache.current[id]?.messages.some((message) => message.id === sourceMessageId)) await loadMessages(id, { sourceMessageId });
  }

  async function editTask(id, taskId, changes) {
    if (mutations.current.has(taskId)) return;
    mutations.current.add(taskId); setTaskBusy((previous) => ({ ...previous, [taskId]: true }));
    try {
      const result = await salesCopilotApi.editTask(taskId, changes);
      updateDetail(id, (detail) => ({ ...detail, tasks: detail.tasks.map((task) => task.id === taskId ? { ...task, ...result.task } : task) }));
    } finally { mutations.current.delete(taskId); setTaskBusy((previous) => ({ ...previous, [taskId]: false })); }
  }

  async function confirmFact(id, field, value) {
    const profile = await salesCopilotApi.confirmProfileFact(id, field, value);
    updateDetail(id, (detail) => ({ ...detail, profile }));
    setItems((previous) => previous.map((item) => item.conversation_id === id ? { ...item, interested_models: profile.interested_models, budget_vnd: profile.budget_vnd } : item));
  }

  async function toggleDraft() {
    if (preferenceBusy || !preferences) return;
    setPreferenceBusy(true);
    try { setPreferences(await salesCopilotApi.updatePreferences({ ...preferences, draft_enabled: !preferences.draft_enabled })); }
    finally { setPreferenceBusy(false); }
  }

  async function generateDraft(id) {
    if (!preferences?.draft_enabled || mutations.current.has(`generate:${id}`)) return;
    mutations.current.add(`generate:${id}`);
    setDraftBusyIds((previous) => ({ ...previous, [id]: true }));
    try { const data = await salesCopilotApi.generateDraft(id, false); setSavedDrafts((previous) => ({ ...previous, [id]: data })); }
    finally { mutations.current.delete(`generate:${id}`); setDraftBusyIds((previous) => ({ ...previous, [id]: false })); }
  }

  async function analyze(id) {
    if (mutations.current.has(`analysis:${id}`)) return;
    mutations.current.add(`analysis:${id}`);
    setAnalysisIds((previous) => ({ ...previous, [id]: true }));
    try {
      const before = detailCache.current[id];
      const result = await salesCopilotApi.analyzeConversation(id);
      const after = await loadDetails(id, true);
      if (!after) throw new Error('Phân tích xong nhưng chưa tải được dữ liệu mới. Hãy làm mới tin nhắn.');
      const changes = [];
      for (const [field, label] of [['interested_models', 'Xe quan tâm'], ['budget_vnd', 'Ngân sách'], ['payment_method', 'Hình thức mua'], ['usage_purpose', 'Nhu cầu'], ['charging_condition', 'Điều kiện sạc'], ['down_payment_vnd', 'Trả trước'], ['purchase_timeline', 'Thời điểm mua']]) {
        if (JSON.stringify(before?.profile?.[field]) !== JSON.stringify(after.profile?.[field])) changes.push(`${label}: ${String(before?.profile?.[field] ?? 'Chưa rõ')} → ${String(after.profile?.[field] ?? 'Chưa rõ')}`);
      }
      if (before?.lead_status?.stage !== after.lead_status?.stage) changes.push('Giai đoạn AI đề xuất đã thay đổi.');
      if (after.lead_status?.stage_source === 'sales') changes.push('Giữ giai đoạn sales đã chọn.');
      const created = after.tasks.filter((task) => !before?.tasks?.some((old) => old.id === task.id)).length;
      changes.push(`${created} đề xuất công việc mới cần duyệt.`, result.status === 'no_messages' ? 'Chưa có tin nhắn để phân tích.' : 'Đã cập nhật tóm tắt; dữ kiện sales xác nhận được giữ nguyên.');
      setAnalysisChanges((previous) => ({ ...previous, [id]: changes }));
    }
    finally { mutations.current.delete(`analysis:${id}`); setAnalysisIds((previous) => ({ ...previous, [id]: false })); }
  }

  async function updateStage(id, stage, reason) {
    if (mutations.current.has(`stage:${id}`)) return;
    mutations.current.add(`stage:${id}`);
    setStageBusyIds((previous) => ({ ...previous, [id]: true }));
    try {
      const lead = await salesCopilotApi.updateLeadStage(id, stage, reason);
      updateDetail(id, (detail) => ({ ...detail, lead_status: lead }));
      setItems((previous) => previous.map((item) => item.conversation_id === id ? { ...item, lead_stage: lead.stage || 'new' } : item));
    } finally { mutations.current.delete(`stage:${id}`); setStageBusyIds((previous) => ({ ...previous, [id]: false })); }
  }

  const customers = useMemo(() => items.map((item, index) => toWorkspaceCustomer(item, details[item.conversation_id], savedDrafts[item.conversation_id], index, now)), [items, details, savedDrafts, now]);
  return { customers, selectedId, selectCustomer: setSelectedId, listStatus, listError, loadList, loadDetails,
    refresh: (id) => Promise.all([loadDetails(id, true), ...(replySuggestionsAvailable ? [loadSavedDraft(id, true)] : [])]),
    detailError: detailErrors[selectedId], loadingDetail: Boolean(pending[selectedId]), sending: Boolean(sendingIds[selectedId]),
    taskBusy, createTask, toggleTask, editTask, confirmFact, sendMessage, loadMessages, ensureSource, loadingOlder: Boolean(pageBusy[selectedId]), analysisChanges: analysisChanges[selectedId], draftEnabled: Boolean(preferences?.draft_enabled), preferenceBusy: preferenceBusy || !preferences,
    toggleDraft, generateDraft, draftBusy: Boolean(draftBusyIds[selectedId]), analyze, analyzing: Boolean(analysisIds[selectedId]),
    updateStage, stageBusy: Boolean(stageBusyIds[selectedId]), searchKnowledge: lookup.ask, knowledge: lookup.state,
    loadKnowledge: lookup.load, setKnowledgeQuery: lookup.setQuery };
}
