export function verifySourceReference(document, reference) {
  if (!reference) return;
  const fields = [['document_id', 'document_id'], ['version', 'version'], ['effective_from', 'effective_date'], ['effective_to', 'expiry_date']];
  for (const [expected, actual] of fields) {
    if (reference[expected] != null && reference[expected] !== document[actual]) {
      throw new Error('Tài liệu trong Kho kiến thức không khớp phiên bản hoặc thời gian hiệu lực của nguồn đã dẫn. Hãy đối chiếu đoạn nguồn trong Copilot.');
    }
  }
}

export function sourceHighlight(document, reference) {
  const content = document.content || '';
  for (const chunk of reference?.chunks || []) {
    const excerpt = chunk.content || chunk.excerpt;
    if (!excerpt?.trim()) continue;
    const start = content.indexOf(excerpt);
    if (start !== -1) return { before: content.slice(0, start), text: excerpt, after: content.slice(start + excerpt.length) };
  }
  return null;
}
