import { useEffect, useRef, useState } from 'react';
import { BookOpen, ChevronRight, RefreshCw, Send } from 'lucide-react';
import { renderMarkdownWithCitations } from '../markdownRenderer';
import { groupCitations } from '../citationGroups';
import { copilotReason } from '../../../lib/copilotStatus';

const STATUS = {
  answered: 'Đã trả lời', partial: 'Trả lời một phần', needs_clarification: 'Cần làm rõ', abstained: 'Chưa đủ căn cứ trả lời',
};

export function CustomerKnowledgeTool({ lookup, onSearch, onLoadHistory, onQueryChange, onOpenDocument }) {
  const [citation, setCitation] = useState(null);
  const log = useRef(null);
  const citationDetail = useRef(null);
  useEffect(() => { citationDetail.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, [citation]);
  const nearBottom = useRef(true);
  const messages = lookup.messages || [];
  const query = lookup.query || '';
  const busy = lookup.busy || lookup.needsSync || lookup.accessDenied;
  useEffect(() => {
    if (nearBottom.current && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messages.length, lookup.pendingQuery, lookup.progress]);
  function submit(event) {
    event?.preventDefault();
    if (query.trim().length >= 2 && !busy) { nearBottom.current = true; void onSearch(query.trim()); }
  }
  function showCitation(source, turnId) { setCitation({ ...source, turnId }); }
  return <div className="sw-knowledge-tool">
    <div className="sw-knowledge-log" ref={log} role="log" aria-label="Lịch sử tra cứu xe" onScroll={() => {
      const node = log.current; nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
    }}>
      {lookup.nextBeforeSeq && <button type="button" className="sw-text-button sw-load-lookup" disabled={lookup.loadingOlder} onClick={() => {
        const node = log.current; const height = node.scrollHeight; const top = node.scrollTop;
        void onLoadHistory(lookup.nextBeforeSeq).then(() => requestAnimationFrame(() => { node.scrollTop = top + node.scrollHeight - height; })).catch(() => {});
      }}>{lookup.loadingOlder ? 'Đang tải…' : 'Xem trao đổi trước'}</button>}
      {lookup.loading && !lookup.loaded && <p className="sw-tool-status" role="status"><RefreshCw size={14} className="sw-spin" />Đang tải lịch sử tra cứu…</p>}
      {!messages.length && !lookup.loading && !lookup.error && !lookup.syncError && <div className="sw-lookup-empty"><BookOpen size={24} /><strong>Kiến thức xe cho sales</strong><p>Chưa có lịch sử tra cứu. Bạn có thể hỏi ngay về giá, so sánh xe và chính sách có nguồn.</p>
        <div className="sw-knowledge-suggestions">{['So sánh VF 3 và VF 5', 'Chính sách bảo hành xe VinFast'].map((text) => <button key={text} type="button" className="sw-secondary-button" disabled={busy} onClick={() => onQueryChange(text)}>{text}<ChevronRight size={12} /></button>)}</div>
      </div>}
      {messages.map((message) => {
        const result = message.response_data || message;
        const sources = groupCitations(result.citations || []);
        const activeCitation = citation?.turnId === message.id ? citation : null;
        return <section key={message.id} className={`sw-lookup-turn sw-lookup-${message.role}`} aria-label={message.role === 'user' ? 'Câu hỏi của sales' : 'Kết quả tra cứu'}>
          <div className="sw-lookup-turn-heading"><strong>{message.role === 'user' ? 'Bạn' : 'Copilot'}</strong>{message.role === 'assistant' && <span className={`sw-lookup-status sw-lookup-status-${result.status}`}>{STATUS[result.status] || result.status}</span>}</div>
          {message.role === 'user' ? <p className="sw-lookup-question">{message.content}</p> : <>
            {renderMarkdownWithCitations(message.content, sources, (source) => showCitation(source, message.id))}
            {copilotReason(result.reason_code) && <p className="sw-freshness">{copilotReason(result.reason_code)}</p>}
            {!!result.missing_information?.length && <ul className="sw-lookup-missing">{result.missing_information.map((item, index) => <li key={index}>{item}</li>)}</ul>}
            {!!sources.length && <details className="sw-knowledge-citations"><summary>Nguồn tham khảo · {sources.length} tài liệu</summary>{sources.map((source) => <button type="button" className="sw-source-button" key={source.group_key} onClick={() => showCitation(source, message.id)}><BookOpen size={14} /><span>[{source.display_number}] {source.title || source.document_id || source.citation_id}{source.version && <small>Phiên bản: {source.version}</small>}{source.effective_from && <small>Hiệu lực từ {source.effective_from}{source.effective_to && ` đến ${source.effective_to}`}</small>}</span><ChevronRight size={12} /></button>)}</details>}
            {result.suggested_next_question && <button type="button" disabled={busy} className="sw-text-button sw-lookup-followup" onClick={() => onQueryChange(result.suggested_next_question)}>{result.suggested_next_question}<ChevronRight size={12} /></button>}
            {result.request_id && <small className="sw-lookup-request-id">Mã tra cứu: {result.request_id}</small>}
          </>}
          {activeCitation && <section ref={citationDetail} className="sw-citation-detail" aria-label="Chi tiết nguồn"><div className="sw-inline-heading"><strong>[{activeCitation.display_number}] {activeCitation.title || activeCitation.document_id || activeCitation.citation_id}</strong><button type="button" className="sw-text-button" onClick={() => setCitation(null)}>Đóng nguồn</button></div><small>{activeCitation.version && `Phiên bản: ${activeCitation.version} · `}{activeCitation.effective_from ? `Hiệu lực từ ${activeCitation.effective_from}` : 'Nguồn chưa cung cấp ngày hiệu lực'}{activeCitation.effective_to && ` đến ${activeCitation.effective_to}`}</small>{onOpenDocument && activeCitation.document_id && <button type="button" className="sw-text-button sw-open-full-source" onClick={() => onOpenDocument(activeCitation.document_id, activeCitation)}>Mở tài liệu đầy đủ trong Kho kiến thức<ChevronRight size={12} /></button>}{activeCitation.chunks.map((chunk, index) => <div className="sw-citation-excerpt" key={`${chunk.citation_id}-${index}`}><small>Đoạn nguồn {chunk.citation_id}</small><p>{chunk.content || chunk.excerpt || 'Chưa có đoạn trích để hiển thị.'}</p></div>)}</section>}
        </section>;
      })}
      {lookup.pendingQuery && <section className="sw-lookup-turn sw-lookup-user"><strong>Bạn</strong><p className="sw-lookup-question">{lookup.pendingQuery}</p></section>}
      {lookup.busy && <p className="sw-tool-status" role="status"><RefreshCw size={14} className="sw-spin" />{lookup.progress || 'Đang kiểm tra tài liệu và nguồn dẫn…'}</p>}
    </div>
    {(lookup.syncError || lookup.error) && <div className="sw-lookup-error" role="alert"><p>{lookup.syncError || lookup.error}</p>{lookup.errorRequestId && <small className="sw-lookup-request-id">Mã tra cứu: {lookup.errorRequestId}</small>}{lookup.needsSync ? <p>Cần tải lại lịch sử để xác nhận kết quả lượt trước khi hỏi tiếp.</p> : lookup.syncError && !lookup.accessDenied && <p>Bạn vẫn có thể tra cứu khi chưa tải được lịch sử.</p>}{(lookup.needsSync || lookup.syncError) && <button type="button" className="sw-text-button" disabled={lookup.loading} onClick={() => { void onLoadHistory().catch(() => {}); }}>Tải lại lịch sử</button>}</div>}
    <form onSubmit={submit} className="sw-knowledge-form">
      <div className="sw-composer-box">
        <textarea
          id="sw-knowledge-query"
          aria-label={messages.length ? 'Hỏi tiếp về xe và chính sách' : 'Câu hỏi về xe và chính sách'}
          value={query}
          maxLength={4000}
          rows={1}
          placeholder="Hỏi về giá, phiên bản, pin, bảo hành…"
          disabled={Boolean(busy)}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit(event);
            }
          }}
        />
        <div className="sw-composer-tools">
          <button className="sw-primary-button sw-send-button" type="submit" aria-label={lookup.busy ? 'Đang tra cứu' : 'Tra cứu'} disabled={Boolean(busy) || query.trim().length < 2}>
            <Send size={15} />
          </button>
        </div>
      </div>
    </form>
  </div>;
}
