import test from 'node:test';
import assert from 'node:assert/strict';
import { copilotApi } from '../src/api/copilotApi.js';

test('sends owned session, explicit empty context, date and domain', async () => {
  const original = globalThis.fetch;
  let seen;
  globalThis.fetch = async (url, options) => {
    seen = { url, ...options };
    return { ok: true, status: 200, json: async () => ({ status: 'partial', session_id: 'a'.repeat(32) }) };
  };
  try {
    const response = await copilotApi.query({ query: ' VF 5? ', session_id: 'a'.repeat(32),
      customer_context: '', target_date: '2026-10-09', domain: 'specs' });
    assert.equal(seen.url, '/api/v1/copilot/query');
    assert.equal(seen.credentials, 'include');
    assert.deepEqual(JSON.parse(seen.body), { query: 'VF 5?', session_id: 'a'.repeat(32),
      customer_context: '', target_date: '2026-10-09', domain: 'specs' });
    assert.equal(response.status, 'partial');
  } finally {
    globalThis.fetch = original;
  }
});

test('reset deletes the server session and skips empty sessions', async () => {
  const original = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url, options) => {
    seen.push({ url, ...options });
    return { ok: true, status: 204 };
  };
  try {
    await copilotApi.resetSession(null);
    assert.equal(seen.length, 0);
    await copilotApi.resetSession('a'.repeat(32));
    assert.equal(seen[0].url, '/api/v1/copilot/sessions/' + 'a'.repeat(32));
    assert.equal(seen[0].method, 'DELETE');
  } finally {
    globalThis.fetch = original;
  }
});
