const text = (value) => typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
const key = (value) => text(value).toLocaleLowerCase('vi').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
const unique = (items, identity) => {
  const result = new Map();
  for (const item of items) {
    const id = identity(item), previous = result.get(id);
    result.set(id, previous?.sourceMessageIds && item.sourceMessageIds
      ? { ...item, sourceMessageIds: [...new Set([...previous.sourceMessageIds, ...item.sourceMessageIds])] } : item);
  }
  return [...result.values()];
};

/** Read concise analyses and legacy memories without another LLM call. */
export function customerIntelligence(memory = {}, profile = {}, sourceAllowed = () => false) {
  const structured = memory.customer_intelligence;
  const sourceIds = (item) => [...new Set((item.source_message_ids || [item.source_message_id]).filter(sourceAllowed))];
  const timeline = memory.timeline || [];
  let keyPoints, outcomes, commitments;
  if (structured) {
    keyPoints = (structured.key_points || []).map((point) => ({
      topic: text(point.topic), question: text(point.question), answer: text(point.answer),
      status: ['answered', 'confirmed', 'irrelevant'].includes(point.status) ? point.status : 'open', sourceMessageIds: sourceIds(point),
    })).filter((point) => point.topic || point.question);
    outcomes = (structured.outcomes || []).map((item) => ({ text: text(item.text), sourceMessageIds: sourceIds(item) }))
      .filter((item) => item.text && item.sourceMessageIds.length);
    commitments = (structured.commitments || []).map((item) => ({
      text: [item.actor, item.action, item.time].map(text).filter(Boolean).join(' — '), sourceMessageIds: sourceIds(item),
    })).filter((item) => item.text && item.sourceMessageIds.length);
  } else {
    keyPoints = timeline.filter((event) => ['consulted', 'inquiry', 'objection'].includes(event.event_type)).map((event) => ({
      topic: text(event.title || event.description), question: event.event_type === 'consulted' ? '' : text(event.description),
      answer: event.event_type === 'consulted' ? text(event.description || event.title) : '',
      status: event.event_type === 'consulted' ? 'answered' : 'open', sourceMessageIds: sourceIds(event),
    }));
    const open = unique([...(memory.pending_items || []), ...(profile.unresolved_questions || [])].map(text).filter(Boolean), key);
    for (const question of open) {
      const existing = keyPoints.find((point) => key(point.topic) === key(question) || key(point.question) === key(question));
      if (existing) existing.status = 'open';
      else keyPoints.push({ topic: question, question: '', answer: '', status: 'open', sourceMessageIds: [] });
    }
    outcomes = timeline.filter((event) => event.event_type === 'resolved' && sourceIds(event).length)
      .map((event) => ({ text: text(event.description || event.title), sourceMessageIds: sourceIds(event) }));
    const promiseEvents = timeline.filter((event) => event.event_type === 'promise');
    commitments = [...promiseEvents.map((event) => ({ text: text(event.description || event.title), sourceMessageIds: sourceIds(event) })),
      ...(memory.key_promises || []).map((promise) => ({ text: text(promise), sourceMessageIds: [] }))];
  }
  outcomes = unique(outcomes.filter((item) => item.text), (item) => key(item.text));
  commitments = unique(commitments.filter((item) => item.text), (item) => key(item.text));
  const dedicated = new Set([...outcomes, ...commitments].map((item) => key(item.text)));
  keyPoints = unique(keyPoints, (point) => key(point.topic || point.question))
    .filter((point) => point.status === 'open' || !dedicated.has(key(point.answer || point.question || point.topic)));
  return { recap: text(memory.quick_summary) || text(memory.detailed_summary), keyPoints, outcomes, commitments };
}
