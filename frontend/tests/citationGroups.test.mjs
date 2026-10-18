import test from 'node:test';
import assert from 'node:assert/strict';
import { groupCitations, inlineCitationGroups } from '../src/components/copilot/citationGroups.js';

const sources = [
  { citation_id: 'C1', document_id: 'price', title: 'Chính sách giá', version: '1', effective_from: '2026-01-01', content: 'Giá A' },
  { citation_id: 'C2', document_id: 'price', title: 'Chính sách giá', version: '1', effective_from: '2026-01-01', content: 'Giá B' },
  { citation_id: 'C3', document_id: 'price', title: 'Chính sách giá', version: '2', effective_from: '2026-06-01', content: 'Giá mới' },
  { citation_id: 'C4', document_id: 'other', title: 'Chính sách giá', version: '1' },
];

test('groups chunks by document and version without merging matching titles', () => {
  const groups = groupCitations(sources);
  assert.equal(groups.length, 3);
  assert.deepEqual(groups.map((group) => group.display_number), [1, 2, 3]);
  assert.deepEqual(groups[0].chunks, sources.slice(0, 2));
  assert.equal(sources[0].display_number, undefined);
});

test('inline references retain only the cited evidence, with one badge per document', () => {
  const groups = groupCitations(sources);
  const selected = inlineCitationGroups(['C2', 'C1', 'C2', 'C3', 'C99'], groups);
  assert.deepEqual(selected.map((group) => group.display_number), [1, 2]);
  assert.deepEqual(selected[0].chunks.map((chunk) => chunk.citation_id), ['C2', 'C1']);
  assert.deepEqual(inlineCitationGroups(['C2'], groups)[0].chunks, [sources[1]]);
  assert.equal(groups[0].chunks.length, 2);
});

test('different applicability dates and missing document IDs stay separate', () => {
  const groups = groupCitations([
    sources[0], { ...sources[0], citation_id: 'C5', effective_from: '2026-02-01' },
    { citation_id: 'C6', title: 'Chính sách giá' }, { citation_id: 'C7', title: 'Chính sách giá' },
    { title: 'Không ID' }, { title: 'Không ID' },
  ]);
  assert.equal(groups.length, 6);
  assert.deepEqual(groupCitations([]), []);
});
