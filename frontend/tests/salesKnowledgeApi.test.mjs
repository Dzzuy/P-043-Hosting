import test from 'node:test';
import assert from 'node:assert/strict';
import { salesKnowledgeApi } from '../src/api/salesKnowledgeApi.js';

test('knowledge request carries only the sales question, with no customer or client session', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/v1/copilot/knowledge/stream');
    assert.equal(options.credentials, 'include');
    assert.deepEqual(JSON.parse(options.body), { query: 'VF 5 giá bao nhiêu?' });
    return { ok: true, body: new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode('event: final\ndata: {"session_id":"owned-by-server","answer":"Đã kiểm chứng"}\n\n'));
      controller.close();
    } }) };
  });
  assert.equal((await salesKnowledgeApi.copilotChatStream(' VF 5 giá bao nhiêu? ')).session_id, 'owned-by-server');
});

test('history pagination uses the authenticated account without a customer ID', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/v1/copilot/knowledge?before_seq=21');
    assert.equal(options.credentials, 'include');
    return { ok: true, json: async () => ({ messages: [], next_before_seq: null }) };
  });
  assert.deepEqual(await salesKnowledgeApi.getLookupHistory(21), { messages: [], next_before_seq: null });
});
