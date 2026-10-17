import test from 'node:test';
import assert from 'node:assert/strict';
import { copilotApi } from '../src/api/copilotApi.js';

test('queryStream throws error if stream terminates before receiving final event', async () => {
  const original = globalThis.fetch;
  const mockChunks = [
    'event: status\ndata: {"step": "analyzing", "text": "Đang phân tích..."}\n\n',
    'event: delta\ndata: {"text": "Giá xe là..."}\n\n',
  ];

  let readIndex = 0;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        cancel: async () => {},
        releaseLock() {},
        read: async () => {
          if (readIndex < mockChunks.length) {
            const encoder = new TextEncoder();
            const chunk = encoder.encode(mockChunks[readIndex++]);
            return { done: false, value: chunk };
          }
          return { done: true, value: undefined };
        },
      }),
    },
  });

  try {
    let statusCalled = false;
    let deltaCalled = false;
    await assert.rejects(
      async () => {
        await copilotApi.queryStream(
          { query: 'VF 5 giá bao nhiêu?' },
          {
            onStatus: () => {
              statusCalled = true;
            },
            onDelta: () => {
              deltaCalled = true;
            },
            onFinal: () => {},
          }
        );
      },
      {
        message: /bị ngắt trước khi hoàn tất/,
      }
    );
    assert.equal(statusCalled, true);
    assert.equal(deltaCalled, true);
  } finally {
    globalThis.fetch = original;
  }
});

test('queryStream dispatches onInsights event and onFinal without swallowing callback errors', async () => {
  const original = globalThis.fetch;
  const mockChunks = [
    'event: delta\ndata: {"text": "VF 5"}\n\n',
    'event: final\ndata: {"answer": "VF 5 giá 496 triệu", "status": "answered"}\n\n',
    'event: insights\ndata: {"product_insights": [{"category": "policy", "title": "Ưu đãi sạc"}]}\n\n',
    'event: done\ndata: {}\n\n',
  ];

  let readIndex = 0;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        cancel: async () => {},
        releaseLock() {},
        read: async () => {
          if (readIndex < mockChunks.length) {
            const encoder = new TextEncoder();
            const chunk = encoder.encode(mockChunks[readIndex++]);
            return { done: false, value: chunk };
          }
          return { done: true, value: undefined };
        },
      }),
    },
  });

  try {
    let finalReceived = false;
    let insightsReceived = false;

    await copilotApi.queryStream(
      { query: 'VF 5 giá bao nhiêu?' },
      {
        onFinal: (data) => {
          finalReceived = true;
          assert.equal(data.status, 'answered');
        },
        onInsights: (data) => {
          insightsReceived = true;
          assert.equal(data.product_insights.length, 1);
        },
      }
    );

    assert.equal(finalReceived, true);
    assert.equal(insightsReceived, true);
  } finally {
    globalThis.fetch = original;
  }
});

test('queryStream rethrows errors thrown from onFinal callback instead of treating as parse error', async () => {
  const original = globalThis.fetch;
  const mockChunks = [
    'event: final\ndata: {"answer": "Test"}\n\n',
    'event: done\ndata: {}\n\n',
  ];

  let readIndex = 0;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        cancel: async () => {},
        releaseLock() {},
        read: async () => {
          if (readIndex < mockChunks.length) {
            const encoder = new TextEncoder();
            const chunk = encoder.encode(mockChunks[readIndex++]);
            return { done: false, value: chunk };
          }
          return { done: true, value: undefined };
        },
      }),
    },
  });

  try {
    await assert.rejects(
      async () => {
        await copilotApi.queryStream(
          { query: 'Test' },
          {
            onFinal: () => {
              throw new Error('Callback specific crash');
            },
          }
        );
      },
      {
        message: 'Callback specific crash',
      }
    );
  } finally {
    globalThis.fetch = original;
  }
});
