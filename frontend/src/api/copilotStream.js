/** Shared SSE transport. A final event contains a checked and persisted response. */
export async function postCopilotStream(url, payload, { onStatus, onDelta, onFinal, onInsights, onError, signal } = {}) {
  let final;
  let reader;
  let callbackFailed = false;
  try {
    const response = await fetch(url, {
      method: 'POST', credentials: 'include', signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw Object.assign(new Error(data.detail || `Lỗi kết nối Copilot (${response.status})`), {
        requestId: response.headers?.get('X-Request-ID'),
      });
    }
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    function notify(callback, data) {
      try { callback?.(data); }
      catch (error) { callbackFailed = true; throw error; }
    }
    function dispatch(block) {
      const lines = block.split('\n');
      const type = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() || 'message';
      const text = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n');
      if (!text) return;
      const data = JSON.parse(text);
      if (type === 'error') throw Object.assign(new Error(data.error || data.detail || 'Lỗi xử lý yêu cầu'), { requestId: data.request_id });
      if (type === 'status') notify(onStatus, data);
      if (type === 'delta') notify(onDelta, data);
      if (type === 'insights') notify(onInsights, data);
      if (type === 'final') { final = data; notify(onFinal, data); }
    }
    while (true) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        dispatch(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
      }
      if (done) { if (buffer.trim()) dispatch(buffer); break; }
    }
    if (!final) throw new Error('Kết nối Copilot bị ngắt trước khi hoàn tất. Kiểm tra lại lịch sử trước khi thử lại.');
    return final;
  } catch (error) {
    // A transport failure after final cannot invalidate a result already committed by the server.
    if (final && !callbackFailed) return final;
    onError?.(error);
    throw error;
  } finally {
    if (reader) { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  }
}
