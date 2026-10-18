import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), cacheDir: '.tmp/vite-ssr-tests', server: { middlewareMode: true, hmr: false }, appType: 'custom', logLevel: 'error' });
const { CustomerKnowledgeTool } = await server.ssrLoadModule('/src/components/copilot/customerWorkspace/CustomerKnowledgeTool.jsx');
const { renderInlineWithCitations } = await server.ssrLoadModule('/src/components/copilot/markdownRenderer.jsx');
const { groupCitations } = await server.ssrLoadModule('/src/components/copilot/citationGroups.js');
test.after(() => server.close());
const sources = [1, 2, 3, 4].map((number) => ({ citation_id: `C${number}`, document_id: 'price', title: 'Chính sách giá', version: '1', effective_from: '2026-01-01', content: `Đoạn ${number}` }));

test('four chunks display as one document and one inline badge per reference cluster', () => {
  const html = renderToStaticMarkup(React.createElement(CustomerKnowledgeTool, {
    lookup: { messages: [{ id: 'turn', role: 'assistant', content: '- Giá A [C1][C2][C3][C4]\n- Giá B [C2]', citations: sources }] },
  }));
  assert.match(html, /Nguồn tham khảo · 1 tài liệu/);
  assert.equal((html.match(/class="sw-source-button"/g) || []).length, 1);
  assert.equal((html.match(/class="sw-inline-citation"/g) || []).length, 2);
  assert.match(html, /Hiệu lực từ 2026-01-01/);
  assert.doesNotMatch(html, /📄|\[C1\]|\[C2\]/);
});

test('clicking inline citation sends only its referenced chunks, and unknown IDs stay visible', () => {
  let selected;
  const nodes = renderInlineWithCitations('Giá B [C2][C4][C99]', groupCitations(sources), (source) => { selected = source; });
  const fragment = nodes.find((node) => React.isValidElement(node));
  const button = fragment.props.children[0][0];
  button.props.onClick();
  assert.deepEqual(selected.chunks.map((chunk) => chunk.citation_id), ['C2', 'C4']);
  assert.match(renderToStaticMarkup(React.createElement(React.Fragment, null, nodes)), /\[C99\]/);
});
