import test from 'node:test';
import assert from 'node:assert/strict';
import { verifySourceReference, sourceHighlight } from '../src/components/knowledge/sourceReference.js';

const document = { document_id: 'price', version: '1', effective_date: '2026-01-01', content: 'Đầu văn bản. Giá 278 triệu. Cuối văn bản.' };
const reference = { document_id: 'price', version: '1', effective_from: '2026-01-01', chunks: [{ excerpt: 'Giá 278 triệu.' }] };
test('opens matching source but rejects changed version, date and identity', () => {
  assert.doesNotThrow(() => verifySourceReference(document, reference));
  for (const changes of [{ version: '2' }, { document_id: 'other' }, { effective_date: '2026-02-01' }]) {
    assert.throws(() => verifySourceReference({ ...document, ...changes }, reference), /không khớp/);
  }
});
test('highlights exact supporting passage without losing full document content', () => {
  const match = sourceHighlight(document, reference);
  assert.equal(match.text, 'Giá 278 triệu.');
  assert.equal(match.before + match.text + match.after, document.content);
  assert.equal(sourceHighlight(document, { chunks: [{ excerpt: 'Không tồn tại' }] }), null);
  assert.equal(sourceHighlight(document, { chunks: [{ excerpt: ' ' }] }), null);
});
