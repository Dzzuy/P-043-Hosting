/** Render real JSX through Vite without a browser; live UI smoke is tracked separately. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const root = fileURLToPath(new URL('..', import.meta.url));
const server = await createServer({ root, cacheDir: '.tmp/vite-ssr-tests', server: { middlewareMode: true, hmr: false }, appType: 'custom', logLevel: 'error' });
const { CustomerKnowledgeTool } = await server.ssrLoadModule('/src/components/copilot/customerWorkspace/CustomerKnowledgeTool.jsx');
const { CopilotView } = await server.ssrLoadModule('/src/components/copilot/CopilotView.jsx');
const { ConversationWorkspace } = await server.ssrLoadModule('/src/components/copilot/customerWorkspace/ConversationWorkspace.jsx');
const { DraftReply, ConversationSummary } = await server.ssrLoadModule('/src/components/copilot/customerWorkspace/ConversationIntelligence.jsx');
const { CustomerToolsDrawer, LeadStageEditor } = await server.ssrLoadModule('/src/components/copilot/customerWorkspace/CustomerToolsDrawer.jsx');
const { toWorkspaceCustomer } = await server.ssrLoadModule('/src/components/copilot/customerWorkspace/workspaceData.js');
test.after(() => server.close());

function render(lookup = {}) {
  return renderToStaticMarkup(React.createElement(CustomerKnowledgeTool, {
    customer: { name: 'Khách kiểm thử', primaryModel: 'VF 5', model: 'VF 5 Plus' }, lookup,
    onSearch() {}, onLoadHistory() {}, onQueryChange() {},
  }));
}

test('default view opens the personal dashboard and defers the customer workspace', () => {
  // Legacy initialization accesses localStorage; the default customer-only view must not mount it.
  assert.equal(typeof globalThis.localStorage, 'undefined');
  const html = renderToStaticMarkup(React.createElement(CopilotView, { currentUser: { user_id: 'test' } }));
  assert.match(html, /Dashboard/);
  assert.match(html, /Lịch sự kiện/);
  assert.doesNotMatch(html, /Không gian tư vấn khách hàng/);
  assert.doesNotMatch(html, /Tra cứu &amp; Hỏi đáp xe|copilot-chat-card|Mở trang tra cứu đầy đủ/);
});

test('lookup offers general questions independently of the selected customer', () => {
  const html = render();
  assert.match(html, /So sánh VF 3 và VF 5/);
  assert.match(html, /Lịch sử tra cứu xe/);
  assert.doesNotMatch(html, /Lịch sử lưu riêng theo tài khoản sales/);
  assert.doesNotMatch(html, /Khách kiểm thử|Tra cứu riêng cho|Ngữ cảnh:/);
  assert.match(html, /maxLength="4000"/);
  assert.doesNotMatch(html, /Mở trang tra cứu đầy đủ|type="date"/);
});

test('shared Copilot drawer works without a selected customer', () => {
  const html = renderToStaticMarkup(React.createElement(CustomerToolsDrawer, { type: 'copilot', customer: null, knowledge: {} }));
  assert.match(html, /Trợ lý Copilot/);
  assert.match(html, /Lịch sử tra cứu xe/);
  assert.doesNotMatch(html, /Ngữ cảnh:|Tra cứu riêng cho/);
});

test('personalized reply suggestions stay hidden even when a saved draft exists', () => {
  const customer = toWorkspaceCustomer({ conversation_id: 'c', customer_name: 'Khách QA' }, { messages: [], profile: {} }, { text: 'Nháp cũ', based_on_message_seq: 0 });
  const html = renderToStaticMarkup(React.createElement(ConversationWorkspace, {
    customer, composerValue: '', draftOpen: true, draftEnabled: true,
  }));
  assert.doesNotMatch(html, /sw-draft-trigger|Nháp cũ|Bật gợi ý/);
  assert.match(html, /Hỏi Copilot/);
});

test('empty lookup history enables the first question and explains the empty state', () => {
  const html = render({ loaded: true, messages: [], query: 'VF 5 Plus giá bao nhiêu?' });
  assert.match(html, /Chưa có lịch sử tra cứu. Bạn có thể hỏi ngay/);
  assert.doesNotMatch(html, /type="submit"[^>]*disabled/);
});

test('loading or failing the initial history does not disable lookup', () => {
  for (const state of [{ loading: true }, { syncError: 'Tải lịch sử quá lâu' }]) {
    const html = render({ ...state, query: 'VF 5 Plus giá bao nhiêu?' });
    assert.doesNotMatch(html, /type="submit"[^>]*disabled/);
  }
  assert.match(render({ syncError: 'Tải lịch sử quá lâu' }), /Tải lại lịch sử/);
});

test('lookup can open before CRM messages load, when empty, or after a CRM load error', () => {
  for (const state of [{ loading: true }, { loading: false }, { loading: false, error: 'Chưa tải được hội thoại' }]) {
    const customer = toWorkspaceCustomer({ conversation_id: 'customer-a', customer_name: 'Khách mới' }, !state.loading && !state.error ? { messages: [] } : undefined);
    const html = renderToStaticMarkup(React.createElement(ConversationWorkspace, { customer, activeTab: 'conversation', composerValue: '', ...state }));
    assert.doesNotMatch(html, /sw-detail-tabs|role="tablist"/);
    assert.match(html, /class="sw-chat-surface"[\s\S]*class="sw-copilot-dock"/);
    const button = [...html.matchAll(/<button\b[^>]*>[\s\S]*?<\/button>/g)].find(([markup]) => markup.includes('Hỏi Copilot'))?.[0];
    assert.ok(button);
    assert.doesNotMatch(button, /disabled/);
  }
});

test('summary opens in the shared drawer and never replaces the message surface', () => {
  const customer = toWorkspaceCustomer({ conversation_id: 'c' }, { messages: [], memory: { quick_summary: 'Nhu cầu đã lưu' } });
  const workspace = renderToStaticMarkup(React.createElement(ConversationWorkspace, { customer, activeTool: 'summary', composerValue: '' }));
  assert.match(workspace, /aria-expanded="true" aria-controls="sw-conversation-summary"/);
  assert.match(workspace, /sw-chat-surface[\s\S]*sw-message-stream/);
  assert.doesNotMatch(workspace, /sw-summary-content|Nhu cầu đã lưu|sw-copilot-dock/);
  const drawer = renderToStaticMarkup(React.createElement(CustomerToolsDrawer, { type: 'summary', customer }));
  assert.match(drawer, /sw-context-drawer[\s\S]*sw-dialog-body[\s\S]*sw-summary-content/);
  assert.match(drawer, /Nhu cầu đã lưu/);
  assert.match(drawer, /Xem mốc chăm sóc/);
  assert.doesNotMatch(drawer, /Thu gọn tóm tắt/);
});

test('draft offers explicit replacement, append and copy only after sales enables it', () => {
  const customer = toWorkspaceCustomer({ conversation_id: 'c' }, { messages: [], profile: {} }, { text: 'Bản nháp', based_on_message_seq: 0 });
  const html = renderToStaticMarkup(React.createElement(DraftReply, { customer, enabled: true, hasComposerText: true }));
  assert.match(html, /Thay thế/); assert.match(html, /Chèn thêm/); assert.match(html, /Sao chép/);
  assert.doesNotMatch(html, /Chèn vào cuối/);
  const off = renderToStaticMarkup(React.createElement(DraftReply, { customer, enabled: false }));
  assert.doesNotMatch(off, /Tạo gợi ý|Thay thế/); assert.match(off, /Bật gợi ý trả lời/);
});

test('summary is compact and explicit; stage editor never renders numeric lead scores', () => {
  const customer = toWorkspaceCustomer({ conversation_id: 'c' }, { messages: [], memory: { quick_summary: 'Nhu cầu đã lưu' }, lead_status: { score: 99 } });
  const summary = renderToStaticMarkup(React.createElement(ConversationSummary, { customer }));
  assert.match(summary, /Recap — Tổng quan/); assert.match(summary, /Xem mốc chăm sóc/);
  assert.doesNotMatch(summary, /Outcomes —|Commitments —|Key Points —|Xem đầy đủ/);
  const stage = renderToStaticMarkup(React.createElement(LeadStageEditor, { customer }));
  assert.doesNotMatch(stage, /99|100|tiềm năng|lead-score/);
  const drawer = renderToStaticMarkup(React.createElement(CustomerToolsDrawer, { type: 'copilot', customer, knowledge: {} }));
  assert.match(drawer, /Kiến thức xe/); assert.doesNotMatch(drawer, /Không gửi cho khách|Theo khách đang chọn/);
});

test('summary and former profile entry show concise intelligence and keep fact editing collapsed', () => {
  const customer = toWorkspaceCustomer({ conversation_id: 'intelligence' }, {
    messages: [{ id: 'm1', sender_role: 'customer' }],
    profile: { interested_models: ['VF 3'], budget_vnd: 300000000, facts: [
      { field: 'budget_vnd', verification_status: 'confirmed', source_message_ids: ['m1'], note: 'Sales xác nhận' },
    ] }, memory: { quick_summary: 'Khách đang cân nhắc.', detailed_summary: 'Đã trao đổi phương án trả góp.',
      pending_items: ['Chờ hồ sơ vay'], key_promises: ['Sales gửi bảng tính chiều nay'], timeline: [
        { event_type: 'consulted', description: 'Tư vấn tài chính', source_message_id: 'm1' },
      ] },
  });
  for (const type of ['summary', 'profile']) {
    const html = renderToStaticMarkup(React.createElement(CustomerToolsDrawer, { type, customer, onConfirmFact() {} }));
    for (const text of ['Bối cảnh khách hàng', 'Recap — Tổng quan', 'Key Points — Nội dung trao đổi', 'Hỏi lịch sử', '300.000.000',
      'Đã xác nhận bởi sales', 'Sửa dữ kiện', 'Tin nguồn 1', 'Tư vấn tài chính', 'Chờ hồ sơ vay']) assert.ok(html.includes(text), text);
    assert.doesNotMatch(html, /Outcomes — Kết quả tư vấn|Diễn biến tư vấn|Hồ sơ hiện tại|Đã trao đổi phương án trả góp/);
    assert.match(html, /<details class="sw-intelligence-section sw-ci-facts"><summary>/);
  }
});

test('intelligence separates facts, recap and history without duplicate commitment lists', () => {
  const customer = toWorkspaceCustomer({ conversation_id: 'four' }, { message_total: 80, messages: [], memory: {
    quick_summary: 'Khách đang chọn lịch lái thử.', detailed_summary: 'Không hiển thị lại diễn biến dài.', customer_intelligence: {
      key_points: [{ topic: 'Sạc', question: 'Sạc tại nhà thế nào?', answer: 'Sales giải thích lắp bộ sạc.', status: 'answered', source_message_ids: ['old-m1'] }],
      outcomes: [{ text: 'Khách chọn VF 6.', source_message_ids: ['old-m2'] }],
      commitments: [{ actor: 'Sales', action: 'Gửi báo giá', time: 'Chiều nay', source_message_ids: ['old-m3'] }],
    },
  } });
  const html = renderToStaticMarkup(React.createElement(ConversationSummary, { customer }));
  for (const label of ['Recap — Tổng quan', 'Key Points — Nội dung trao đổi', 'Hỏi lịch sử', 'Sales đã trả lời', 'Tin nguồn 1']) assert.ok(html.includes(label));
  assert.doesNotMatch(html, /Không hiển thị lại diễn biến dài/);
  assert.equal(html.split('Khách chọn VF 6.').length - 1, 0);
  assert.doesNotMatch(html, /Outcomes — Kết quả tư vấn|Commitments — Cam kết/);
});

test('access errors disable lookup and show the actual reason', () => {
  const html = render({ query: 'VF 5?', accessDenied: true, syncError: 'Hội thoại chưa được gán cho bạn.' });
  assert.match(html, /chưa được gán cho bạn/);
  assert.match(html, /type="submit"[^>]*disabled=""/);
  assert.doesNotMatch(html, /Bạn vẫn có thể tra cứu/);
});

test('restored checked answers include status, sources and request ID', () => {
  const html = render({ messages: [{ id: 'a1', role: 'assistant', seq: 2, content: 'Giá đã đối chiếu [C1].', response_data: {
    status: 'answered', request_id: 'request-restored', citations: [{ citation_id: 'C1', title: 'Bảng giá chính thức' }],
  } }] });
  assert.match(html, /Đã trả lời/); assert.match(html, /Bảng giá chính thức/); assert.match(html, /request-restored/);
});

test('partial and abstention have separate labels and missing information remains visible', () => {
  const partial = render({ messages: [{ id: 'p1', role: 'assistant', content: 'Có dữ kiện về VF 5.', response_data: {
    status: 'partial', missing_information: ['Nguồn chưa nêu chuẩn NEDC'], reason_code: 'insufficient_evidence',
  } }] });
  assert.match(partial, /Trả lời một phần/); assert.match(partial, /Nguồn chưa nêu chuẩn NEDC/);
  const abstained = render({ messages: [{ id: 'a1', role: 'assistant', content: 'Chưa xác minh được.', response_data: { status: 'abstained' } }] });
  assert.match(abstained, /Chưa đủ căn cứ trả lời/);
});

test('clarification keeps a follow-up composer and previous customer questions', () => {
  const html = render({ messages: [
    { id: 'u1', role: 'user', seq: 1, content: 'Thế còn bản Plus?' },
    { id: 'a1', role: 'assistant', seq: 2, content: 'Bạn đang hỏi mẫu xe nào?', response_data: { status: 'needs_clarification' } },
  ] });
  assert.match(html, /Cần làm rõ/); assert.match(html, /Thế còn bản Plus/); assert.match(html, /Hỏi tiếp về xe và chính sách/);
});

test('progress displays no unverified assistant draft', () => {
  const html = render({ busy: true, pendingQuery: 'So sánh VF 3 với VF 5', progress: 'Đang kiểm chứng nguồn' });
  assert.match(html, /Đang kiểm chứng nguồn/); assert.match(html, /So sánh VF 3 với VF 5/);
  assert.doesNotMatch(html, /sw-lookup-assistant/);
});

test('history synchronization failure blocks another question and offers read-only recovery', () => {
  const html = render({ query: 'Thử lại VF 5?', syncError: 'Chưa tải được lịch sử', needsSync: true });
  assert.match(html, /Chưa tải được lịch sử/); assert.match(html, /Tải lại lịch sử/);
  assert.match(html, /type="submit"[^>]*disabled=""/);
});
