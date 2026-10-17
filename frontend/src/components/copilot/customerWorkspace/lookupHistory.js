export function mergeLookupMessages(previous = [], incoming = []) {
  const messages = new Map();
  for (const message of [...previous, ...incoming]) {
    const key = message.request_id ? `${message.request_id}:${message.role}` : message.id;
    messages.set(key, message);
  }
  return [...messages.values()].sort((a, b) => a.seq - b.seq);
}

export function lookupResultMessages(query, response, lastSeq = 0) {
  const shared = { request_id: response.request_id, created_at: response.answered_at };
  return [
    { ...shared, id: `${response.request_id}:user`, seq: lastSeq + 1, role: 'user', content: query },
    { ...shared, id: `${response.request_id}:assistant`, seq: lastSeq + 2, role: 'assistant', content: response.answer, response_data: response },
  ];
}
