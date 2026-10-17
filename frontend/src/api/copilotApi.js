import { request } from './client.js';
import { postCopilotStream } from './copilotStream.js';

export const copilotApi = {
  async query({ query, target_date, session_id, customer_context, domain }) {
    return request('/copilot/query', {
      method: 'POST',
      body: JSON.stringify({
        query: query.trim(),
        target_date: target_date || undefined,
        session_id: session_id || undefined,
        customer_context,
        domain,
      }),
    });
  },

  async queryStream({ query, target_date, session_id, customer_context, domain }, callbacks) {
    return postCopilotStream('/api/v1/copilot/query/stream', {
      query: query.trim(), target_date: target_date || undefined,
      session_id: session_id || undefined, customer_context, domain,
    }, callbacks);
  },

  async getSessions() {
    return request('/copilot/sessions', {
      method: 'GET',
    });
  },

  async getSessionDetail(sessionId) {
    if (!sessionId) return null;
    return request(`/copilot/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'GET',
    });
  },

  async resetSession(sessionId) {
    if (!sessionId) return;
    return request(`/copilot/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  },

  async deleteSession(sessionId) {
    if (!sessionId) return;
    return request(`/copilot/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  },

  async getSource(documentId, chunkId = null) {
    const query = chunkId ? `?chunk_id=${encodeURIComponent(chunkId)}` : '';
    return request(`/copilot/sources/${encodeURIComponent(documentId)}${query}`, {
      method: 'GET',
    });
  },

  async ingest() {
    return request('/copilot/ingest', {
      method: 'POST',
    });
  },
};
