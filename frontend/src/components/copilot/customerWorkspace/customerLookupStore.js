import { lookupResultMessages, mergeLookupMessages } from './lookupHistory.js';

const ACCESS_ERRORS = new Set([401, 403, 404]);

function historyError(error) {
  if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để tra cứu.';
  if (error.status === 403) return 'Tài khoản này không có quyền sử dụng Copilot.';
  if (error.status === 404) return 'Dịch vụ Copilot chưa khả dụng. Hãy tải lại hoặc liên hệ quản trị viên.';
  return error.message || 'Chưa tải được lịch sử tra cứu.';
}

/** Private state per sales account, shared across CRM customers. */
export function createSalesLookupStore(api) {
  let entries = {};
  const listeners = new Set();
  const requests = new Map();
  const controllers = new Map();
  const get = (key) => entries[key] || {};
  function update(key, values) {
    const previous = get(key);
    entries = { ...entries, [key]: { ...previous, ...(typeof values === 'function' ? values(previous) : values) } };
    for (const listener of listeners) listener();
  }

  function load(key, beforeSeq = null, force = false) {
    const requestKey = `${key}:${beforeSeq || 'latest'}`;
    const previous = requests.get(requestKey);
    if (previous && !force) return previous.promise;
    const cached = get(key);
    if (!force && !beforeSeq && cached.loaded && !cached.needsSync && !cached.accessDenied && !cached.syncError && Date.now() - cached.loadedAt < 30000) {
      return Promise.resolve({ session_id: cached.sessionId, messages: cached.messages, next_before_seq: cached.nextBeforeSeq });
    }
    // A read started before submission cannot confirm whether that submission was saved.
    previous?.controller.abort();
    const turnVersion = get(key).turnVersion || 0;
    const request = { controller: new AbortController() };
    const loadingField = beforeSeq ? 'loadingOlder' : 'loading';
    update(key, { [loadingField]: true });
    request.promise = Promise.resolve().then(() => api.getLookupHistory(beforeSeq, { signal: request.controller.signal })).then((page) => {
      if (request.controller.signal.aborted || (get(key).turnVersion || 0) !== turnVersion) return page;
      update(key, (entry) => ({
        messages: mergeLookupMessages(entry.messages, page.messages), nextBeforeSeq: page.next_before_seq,
        ...(!beforeSeq && { loaded: true, loadedAt: Date.now(), sessionId: page.session_id, needsSync: false, syncError: '', accessDenied: false }),
      }));
      return page;
    }).catch((error) => {
      if (!request.controller.signal.aborted && (get(key).turnVersion || 0) === turnVersion) {
        update(key, (entry) => ({ syncError: historyError(error), accessDenied: entry.accessDenied || ACCESS_ERRORS.has(error.status) }));
      }
      throw error;
    }).finally(() => {
      if (requests.get(requestKey) === request) {
        requests.delete(requestKey);
        update(key, { [loadingField]: false });
      }
    });
    requests.set(requestKey, request);
    return request.promise;
  }

  async function ask(key, text) {
    const query = text.trim();
    const entry = get(key);
    if (entry.busy || entry.needsSync || entry.accessDenied || query.length < 2) return false;
    const controller = new AbortController();
    controllers.set(key, controller);
    update(key, { busy: true, turnVersion: (entry.turnVersion || 0) + 1, error: '', syncError: '', errorRequestId: '', pendingQuery: query, progress: 'Đang phân tích câu hỏi…' });
    try {
      const result = await api.copilotChatStream(query, {
        signal: controller.signal, onStatus: (status) => update(key, { progress: status.text || '' }),
      });
      if (result.reason_code === 'input_blocked') {
        update(key, { error: result.answer, pendingQuery: '' });
        return false;
      }
      update(key, (current) => ({
        messages: mergeLookupMessages(current.messages, lookupResultMessages(query, result, current.messages?.at(-1)?.seq || 0)),
        sessionId: result.session_id, pendingQuery: '', query: current.query?.trim() === query ? '' : current.query,
        loaded: true, error: '', needsSync: false,
      }));
      // Final is already persisted. Refresh IDs in the background without locking the composer.
      void load(key, null, true).catch(() => {});
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      update(key, { error: error.message, errorRequestId: error.requestId, pendingQuery: '', needsSync: true });
      // Read only: reconnect never resends the query or calls the LLM again.
      void load(key, null, true).catch(() => {});
      return false;
    } finally {
      controllers.delete(key);
      update(key, { busy: false, progress: '', pendingQuery: '' });
    }
  }

  return {
    getSnapshot: () => entries,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    load, ask,
    setQuery: (key, query) => update(key, { query }),
    abort() {
      for (const controller of controllers.values()) controller.abort();
      for (const request of requests.values()) request.controller.abort();
    },
  };
}
