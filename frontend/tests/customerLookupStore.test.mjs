import test from 'node:test';
import assert from 'node:assert/strict';
import { setImmediate } from 'node:timers/promises';
import { createSalesLookupStore } from '../src/components/copilot/customerWorkspace/customerLookupStore.js';
import { salesKnowledgeApi } from '../src/api/salesKnowledgeApi.js';
import { lookupResultMessages } from '../src/components/copilot/customerWorkspace/lookupHistory.js';

const empty = { session_id: null, messages: [], next_before_seq: null };
const result = { request_id: 'request-first', session_id: 'session-first', status: 'answered', answer: 'Giá xe đã xác minh [C1].', citations: [{ citation_id: 'C1', chunk_id: 'vf5_4' }] };
const saved = { ...empty, session_id: result.session_id, messages: lookupResultMessages('VF 5?', result) };
const key = 'sales-a';
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('empty history allows the first question and keeps sources from the persisted answer', async () => {
  let posts = 0;
  const store = createSalesLookupStore({
    async getLookupHistory() { return posts ? saved : empty; },
    async copilotChatStream(query) { posts++; assert.equal(query, 'VF 5?'); return result; },
  });
  await store.load(key);
  assert.deepEqual(store.getSnapshot()[key].messages, []);
  store.setQuery(key, 'VF 5?');
  assert.equal(await store.ask(key, ' VF 5? '), true);
  await setImmediate();
  const entry = store.getSnapshot()[key];
  assert.equal(posts, 1);
  assert.equal(entry.messages.length, 2);
  assert.deepEqual(entry.messages[1].response_data.citations, result.citations);
  assert.equal(entry.query, '');
  assert.equal(entry.busy, false);
});

test('a slow initial read does not block submission and cannot erase the new session', async () => {
  const initial = deferred(), refresh = deferred();
  let reads = 0, posts = 0, initialSignal;
  const store = createSalesLookupStore({
    getLookupHistory(before, { signal }) { reads++; if (reads === 1) initialSignal = signal; return reads === 1 ? initial.promise : refresh.promise; },
    async copilotChatStream() { posts++; return result; },
  });
  const loading = store.load(key);
  await setImmediate();
  assert.equal(store.getSnapshot()[key].loading, true);
  assert.equal(await store.ask(key, 'VF 5?'), true);
  assert.equal(posts, 1);
  assert.equal(store.getSnapshot()[key].busy, false);
  assert.equal(initialSignal.aborted, true);
  initial.resolve(empty);
  await loading;
  assert.equal(store.getSnapshot()[key].sessionId, result.session_id);
  assert.equal(store.getSnapshot()[key].messages.length, 2);
  assert.equal(store.getSnapshot()[key].loading, true);
  refresh.resolve(saved);
  await setImmediate();
  assert.equal(store.getSnapshot()[key].loading, false);
});

test('an initial history service failure offers retry without preventing a question', async () => {
  let reads = 0, posts = 0;
  const store = createSalesLookupStore({
    async getLookupHistory() { if (++reads === 1) throw Object.assign(new Error('Không thể tải lịch sử'), { status: 503 }); return saved; },
    async copilotChatStream() { posts++; return result; },
  });
  await assert.rejects(store.load(key), /Không thể tải/);
  assert.equal(store.getSnapshot()[key].needsSync, undefined);
  assert.equal(await store.ask(key, 'VF 5?'), true);
  assert.equal(posts, 1);
  await setImmediate();
});

for (const [status, message] of [[401, /Đăng nhập lại/], [403, /không có quyền/], [404, /chưa khả dụng/]]) {
  test(`history ${status} explains the access problem and never bypasses it`, async () => {
    let allowed = false, posts = 0;
    const store = createSalesLookupStore({
      async getLookupHistory() { if (!allowed) throw Object.assign(new Error('access error'), { status }); return empty; },
      async copilotChatStream() { posts++; return result; },
    });
    await assert.rejects(store.load(key));
    assert.match(store.getSnapshot()[key].syncError, message);
    assert.equal(await store.ask(key, 'VF 5?'), false);
    assert.equal(posts, 0);
    allowed = true;
    await store.load(key);
    assert.equal(await store.ask(key, 'VF 5?'), true);
    await setImmediate();
  });
}

test('a disconnected submission stays locked until a fresh latest page confirms history', async () => {
  const initial = deferred();
  let reads = 0, posts = 0, restore = false;
  const store = createSalesLookupStore({
    async getLookupHistory(before) {
      reads++;
      if (reads === 1) return initial.promise;
      if (before) return { ...empty, messages: [{ id: 'old', seq: 1, role: 'user', content: 'Câu cũ' }] };
      if (!restore) throw new Error('Tải lịch sử thất bại');
      return saved;
    },
    async copilotChatStream() { posts++; throw new Error('Kết nối bị ngắt'); },
  });
  const oldRead = store.load(key);
  await setImmediate();
  assert.equal(await store.ask(key, 'VF 5?'), false);
  await setImmediate();
  assert.equal(store.getSnapshot()[key].needsSync, true);
  initial.resolve(empty);
  await oldRead;
  assert.equal(store.getSnapshot()[key].needsSync, true);
  await store.load(key, 5);
  assert.equal(store.getSnapshot()[key].needsSync, true);
  assert.equal(await store.ask(key, 'VF 5?'), false);
  assert.equal(posts, 1);
  restore = true;
  await store.load(key);
  assert.equal(store.getSnapshot()[key].needsSync, false);
  assert.equal(store.getSnapshot()[key].messages.at(-1).response_data.request_id, result.request_id);
  assert.equal(posts, 1); // Reconciliation never resends a question.
});

test('customer switches keep the same in-flight turn and newer query; other accounts stay isolated', async () => {
  const first = deferred();
  let posts = 0;
  const store = createSalesLookupStore({
    async getLookupHistory() { return empty; },
    async copilotChatStream() { posts++; return first.promise; },
  });
  store.setQuery(key, 'VF 5?');
  const ask = store.ask(key, 'VF 5?');
  assert.equal(await store.ask(key, 'VF 6?'), false);
  store.setQuery(key, 'VF 6?');
  store.setQuery('sales-b', 'VF 3?');
  first.resolve(result);
  await ask;
  await setImmediate();
  assert.equal(posts, 1);
  assert.equal(store.getSnapshot()[key].messages.length, 2);
  assert.equal(store.getSnapshot()[key].query, 'VF 6?');
  assert.equal(store.getSnapshot()['sales-b'].messages, undefined);
});

test('history HTTP timeout is bounded, reports the cause and never posts a query', async (t) => {
  t.mock.method(AbortSignal, 'timeout', (ms) => {
    assert.equal(ms, 45000);
    return AbortSignal.abort(new DOMException('Timed out', 'TimeoutError'));
  });
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(options.method, undefined);
    assert.match(url, /copilot\/knowledge$/);
    options.signal.throwIfAborted();
  });
  await assert.rejects(salesKnowledgeApi.getLookupHistory(), /Tải lịch sử quá lâu/);
});

test('reopening a drawer uses fresh private history; expiration and forced sync fetch again', async (t) => {
  let now = 100000, reads = 0;
  t.mock.method(Date, 'now', () => now);
  const store = createSalesLookupStore({ async getLookupHistory() { reads++; return saved; } });
  await store.load(key);
  await store.load(key);
  assert.equal(reads, 1);
  now += 30001;
  await store.load(key);
  assert.equal(reads, 2);
  await store.load(key, null, true);
  assert.equal(reads, 3);
  await store.load('sales-b');
  assert.equal(reads, 4, 'Another owner must never reuse the first owner’s cached history');
});
