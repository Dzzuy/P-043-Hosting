import { request } from './client.js';
import { postCopilotStream } from './copilotStream.js';

export const salesKnowledgeApi = {
  async getLookupHistory(beforeSeq = null, { signal } = {}) {
    const page = beforeSeq ? `?before_seq=${encodeURIComponent(beforeSeq)}` : '';
    const timeout = AbortSignal.timeout(45000);
    try {
      return await request(`/copilot/knowledge${page}`, {
        signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      });
    } catch (error) {
      if (timeout.aborted && !signal?.aborted) error.message = 'Tải lịch sử quá lâu. Bạn có thể thử tải lại.';
      throw error;
    }
  },
  async copilotChatStream(query, callbacks) {
    return postCopilotStream('/api/v1/copilot/knowledge/stream', { query: query.trim() }, callbacks);
  },
};
