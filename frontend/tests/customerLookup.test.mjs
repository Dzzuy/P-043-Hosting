import test from 'node:test';
import assert from 'node:assert/strict';
import { postCopilotStream } from '../src/api/copilotStream.js';
import { lookupResultMessages, mergeLookupMessages } from '../src/components/copilot/customerWorkspace/lookupHistory.js';

function responseFrom(chunks, { failAfter = false } = {}) {
  let index = 0;
  return {
    ok: true,
    body: new ReadableStream({
      pull(controller) {
        if (index < chunks.length) controller.enqueue(chunks[index++]);
        else if (failAfter) controller.error(new Error('connection closed'));
        else controller.close();
      },
    }),
  };
}

test('SSE handles split Vietnamese UTF-8, CRLF, status and final without trailing separator', async () => {
  const original = globalThis.fetch;
  const answer = { answer: 'Đã xác minh giá xe và điều kiện áp dụng.', request_id: 'req', citations: [{ citation_id: 'C1' }] };
  const bytes = new TextEncoder().encode(`event: status\r\ndata: {"text":"Đang kiểm chứng"}\r\n\r\nevent: final\r\ndata: ${JSON.stringify(answer)}`);
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(options.credentials, 'include');
    assert.deepEqual(JSON.parse(options.body), { query: 'VF 5?' });
    return responseFrom([...bytes].map((byte) => new Uint8Array([byte])));
  };
  try {
    const statuses = [];
    const result = await postCopilotStream('/lookup', { query: 'VF 5?' }, { onStatus: (value) => statuses.push(value.text) });
    assert.deepEqual(result, answer);
    assert.deepEqual(statuses, ['Đang kiểm chứng']);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('SSE error is reported once and never resubmits the question', async () => {
  const original = globalThis.fetch;
  let calls = 0; let errors = 0; let finals = 0;
  globalThis.fetch = async () => { calls++; return responseFrom([new TextEncoder().encode('event: error\ndata: {"detail":"Dịch vụ tạm thời không khả dụng","request_id":"request-error"}\n\n')]); };
  try {
    await assert.rejects(postCopilotStream('/lookup', { query: 'VF 5?' }, {
      onError: (error) => { errors++; assert.equal(error.requestId, 'request-error'); }, onFinal: () => finals++,
    }), /Dịch vụ/);
    assert.equal(calls, 1); assert.equal(errors, 1); assert.equal(finals, 0);
  } finally { globalThis.fetch = original; }
});

test('interruption before final fails, but interruption after persisted final keeps the result', async () => {
  const original = globalThis.fetch;
  const encode = (value) => new TextEncoder().encode(value);
  try {
    globalThis.fetch = async () => responseFrom([encode('event: status\ndata: {"text":"Đang tra cứu"}\n\n')]);
    await assert.rejects(postCopilotStream('/lookup', {}), /ngắt trước khi hoàn tất/);
    globalThis.fetch = async () => responseFrom([encode('event: final\ndata: {"answer":"Đã lưu"}\n\n')], { failAfter: true });
    assert.deepEqual(await postCopilotStream('/lookup', {}), { answer: 'Đã lưu' });
  } finally { globalThis.fetch = original; }
});

test('history reconciliation replaces provisional IDs and preserves source metadata', () => {
  const response = { request_id: 'request-1', answer: 'Trả lời [C1]', status: 'partial', citations: [{ chunk_id: 'vf5_4' }], missing_information: ['NEDC'] };
  const provisional = lookupResultMessages('VF 5?', response);
  const saved = provisional.map((message, index) => ({ ...message, id: `db-${index}`, seq: index + 5 }));
  const merged = mergeLookupMessages(provisional, saved);
  assert.equal(merged.length, 2);
  assert.deepEqual(merged.map((message) => message.id), ['db-0', 'db-1']);
  assert.deepEqual(merged[1].response_data, response);
});

test('older pages prepend by sequence without duplicating loaded turns', () => {
  const first = { id: '1', seq: 1, role: 'user', request_id: 'r1' };
  const second = { id: '2', seq: 2, role: 'assistant', request_id: 'r1' };
  const third = { id: '3', seq: 3, role: 'user', request_id: 'r2' };
  assert.deepEqual(mergeLookupMessages([second, third], [first, second]), [first, second, third]);
});
