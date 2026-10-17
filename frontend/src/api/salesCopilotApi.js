import { request } from './client.js';
import { postCopilotStream } from './copilotStream.js';
import { notifyAgendaChange } from '../components/copilot/agenda/agendaResource.js';

async function mutate(endpoint, options) {
  const result = await request(endpoint, options);
  notifyAgendaChange();
  return result;
}

export const salesCopilotApi = {
  getDashboard(params = {}) { return request(`/sales-copilot/dashboard?${new URLSearchParams(params)}`); },
  getCalendar(week) { return request(`/sales-copilot/calendar?week_start=${week}`); },
  createPersonalTask(task) { return mutate('/sales-copilot/tasks', { method: 'POST', body: JSON.stringify(task) }); },
  getTaskOverlaps(params) { return request(`/sales-copilot/tasks/overlaps?${new URLSearchParams(params)}`); },
  async getConversations() {
    return request('/sales-copilot/conversations');
  },

  async getConversationDetails(conversationId) {
    return request(`/sales-copilot/conversations/${conversationId}?message_limit=30`);
  },

  async getMessagePage(conversationId, { beforeSeq, sourceMessageId } = {}) {
    const params = new URLSearchParams({ limit: '30' });
    if (beforeSeq) params.set('before_seq', beforeSeq);
    if (sourceMessageId) params.set('source_message_id', sourceMessageId);
    return request(`/sales-copilot/conversations/${conversationId}/messages?${params}`);
  },

  async confirmProfileFact(conversationId, field, value) {
    return mutate(`/sales-copilot/conversations/${conversationId}/profile-fact`, { method: 'PATCH', body: JSON.stringify({ field, value }) });
  },

  async editTask(taskId, changes) {
    return mutate(`/sales-copilot/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify(changes) });
  },

  async sendMessage(conversationId, content) {
    return mutate(`/sales-copilot/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, sender_role: 'sales' }),
    });
  },

  async analyzeConversation(conversationId) {
    return mutate(`/sales-copilot/conversations/${conversationId}/analyze`, {
      method: 'POST',
    });
  },

  async getPreferences() {
    return request('/sales-copilot/preferences');
  },

  async updatePreferences(preferences) {
    return request('/sales-copilot/preferences', {
      method: 'PATCH',
      body: JSON.stringify(preferences),
    });
  },

  async getNextBestActions(conversationId, force = false) {
    return request(`/sales-copilot/conversations/${conversationId}/recommendations?force=${force}`, {
      method: 'POST',
    });
  },

  async generateDraft(conversationId, force = false) {
    return request(`/sales-copilot/conversations/${conversationId}/draft?force=${force}`, {
      method: 'POST',
    });
  },

  async getSavedDraft(conversationId) {
    return request(`/sales-copilot/conversations/${conversationId}/draft`);
  },

  async createTask(conversationId, task) {
    return mutate(`/sales-copilot/conversations/${conversationId}/tasks`, {
      method: 'POST',
      body: JSON.stringify(task),
    });
  },

  async copilotChat(conversationId, query) {
    return request(`/sales-copilot/conversations/${conversationId}/copilot-chat`, {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  },

  async copilotChatStream(conversationId, query, callbacks) {
    return postCopilotStream(`/api/v1/sales-copilot/conversations/${encodeURIComponent(conversationId)}/copilot-chat/stream`, { query }, callbacks);
  },

  async getLookupHistory(conversationId, beforeSeq = null, { signal } = {}) {
    const page = beforeSeq ? `?before_seq=${beforeSeq}` : '';
    const timeout = AbortSignal.timeout(45000);
    try {
      return await request(`/sales-copilot/conversations/${encodeURIComponent(conversationId)}/copilot-chat${page}`, {
        signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      });
    } catch (error) {
      if (timeout.aborted && !signal?.aborted) error.message = 'Tải lịch sử quá lâu. Bạn có thể thử tải lại.';
      throw error;
    }
  },

  async updateLeadStage(conversationId, stage, reason = '') {
    return mutate(`/sales-copilot/conversations/${conversationId}/lead-stage`, {
      method: 'PATCH',
      body: JSON.stringify({ stage, reason }),
    });
  },

  async updateTaskStatus(taskId, status) {
    return mutate(`/sales-copilot/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  },

  async seedDemoData() {
    return request('/sales-copilot/seed-demo-data', {
      method: 'POST',
    });
  },
};
