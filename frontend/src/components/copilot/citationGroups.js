// A missing document ID cannot safely be grouped by title alone.
export function groupCitations(citations = []) {
  const groups = [];
  const byKey = new Map();
  for (const [index, source] of citations.entries()) {
    const key = JSON.stringify([
      source.document_id || `citation:${source.citation_id || index}`,
      source.version ?? null,
      source.effective_from ?? null,
      source.effective_to ?? null,
    ]);
    let group = byKey.get(key);
    if (!group) {
      group = { ...source, group_key: key, display_number: groups.length + 1, chunks: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    group.chunks.push(source);
  }
  return groups;
}

export function inlineCitationGroups(ids, groups) {
  const selected = new Map();
  for (const id of ids) {
    const group = groups.find((item) => item.chunks.some((chunk) => chunk.citation_id === id));
    if (!group) continue;
    if (!selected.has(group.group_key)) selected.set(group.group_key, { ...group, chunks: [] });
    const target = selected.get(group.group_key);
    for (const chunk of group.chunks.filter((item) => item.citation_id === id)) {
      if (!target.chunks.includes(chunk)) target.chunks.push(chunk);
    }
  }
  return [...selected.values()];
}
