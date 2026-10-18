import { useEffect, useState } from 'react';
import { Send } from 'lucide-react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { CHANGE_EVENT } from '../agenda/agendaResource';
import { displayDateTime } from './workspaceData';
import { TaskEditor } from './CreateTaskDialog';

function HistoricalSource({ customerId, analysisId, evidence }) {
  const [message, setMessage] = useState(null);
  const [error, setError] = useState('');
  return <details><summary>Tin nguồn</summary><blockquote>{evidence.quote}</blockquote>
    <button type="button" className="sw-text-button" onClick={async () => {
      try { setMessage(await salesCopilotApi.getAnalyzedSource(customerId, analysisId, evidence.message_id)); }
      catch (failure) { setError(failure.message); }
    }}>Xem bản tin gốc trong phiên</button>
    {message && <p>{message.sender_role === 'customer' ? 'Khách' : 'Sales'} · {displayDateTime(message.sent_at)}: {message.content}</p>}
    {error && <p role="alert">{error}</p>}
  </details>;
}

export function CustomerHistory({ customer }) {
  const [state, setState] = useState(null);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);
  useEffect(() => {
    let stopped = false;
    const load = () => salesCopilotApi.getIntelligence(customer.customerId).then((data) => { if (!stopped) { setState(data); setError(''); } }).catch((failure) => { if (!stopped) setError(failure.message); });
    const onVisibility = () => { if (typeof document !== 'undefined' && document.visibilityState === 'visible') void load(); };
    void load();
    window.addEventListener(CHANGE_EVENT, load);
    document.addEventListener('visibilitychange', onVisibility);
    const timer = setInterval(() => {
      if (typeof document === 'undefined' || document.visibilityState !== 'hidden') void load();
    }, 15000);
    return () => {
      stopped = true;
      clearInterval(timer);
      window.removeEventListener(CHANGE_EVENT, load);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [customer.customerId, customer.analysisVersion]);
  const refresh = async () => setState(await salesCopilotApi.getIntelligence(customer.customerId));
  const review = async (proposal, approve, changes = {}) => {
    setBusy(true); setError('');
    const { title, priority, starts_at, ends_at, location, description, item_type } = changes;
    const edits = Object.fromEntries(Object.entries({ title, priority, starts_at, ends_at, location, description, item_type }).filter(([, value]) => value !== undefined));
    try { await salesCopilotApi.reviewProposal(customer.customerId, proposal.id, approve, edits); setEditing(null); await refresh(); }
    catch (failure) { setError(failure.message); throw failure; }
    finally { setBusy(false); }
  };
  const proposals = (state?.proposals || []).filter((p) => p.status === 'pending');

  async function submitQuestion(event) {
    event?.preventDefault();
    if (busy || !state?.analysis_id || !query.trim()) return;
    setBusy(true); setError('');
    try {
      await salesCopilotApi.historyChat(customer.customerId, state.analysis_id, query.trim());
      setQuery('');
      await refresh();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <div className="sw-ci-bottom-stack" aria-label="Đề xuất và hỏi đáp lịch sử">
    {state?.requires_reanalysis && <p className="sw-freshness">Tin cũ đã thay đổi. Cần phân tích lại; hỏi đáp hiện dùng bản lưu trước đây.</p>}
    {error && <p className="sw-error-banner" role="alert">{error}</p>}

    {!!proposals.length && <section className="sw-ci-section sw-ci-proposals">
      <h3>Đề xuất công việc cần duyệt <span>({proposals.length})</span></h3>
      {proposals.map((p) => <article key={p.id} className="sw-ci-proposal-card">
        <div className="sw-ci-proposal-head">
          <strong>{p.action}</strong>
          <span className="sw-ci-status is-open">{p.operation === 'cancel' ? 'Đề xuất hủy' : p.operation === 'update' ? 'Đề xuất sửa' : 'Đề xuất tạo'}</span>
        </div>
        {p.evidence.map((e, i) => <details key={i}><summary>Xem câu trích dẫn nguồn</summary><blockquote>{e.quote}</blockquote></details>)}
        {editing === p.id && p.operation !== 'cancel' ? (
          <TaskEditor customer={customer} task={{ title: p.action, item_type: p.event_type === 'appointment' ? 'appointment' : 'task', starts_at: p.starts_at, ends_at: p.ends_at, location: p.location }} onCancel={() => setEditing(null)} onSave={(changes) => review(p, true, changes)} />
        ) : (
          <div className="sw-inline-actions">
            <button type="button" className="sw-text-button" disabled={busy} onClick={() => { void review(p, false).catch(() => {}); }}>Bác đề xuất</button>
            <button type="button" className="sw-secondary-button" disabled={busy} onClick={() => { if (p.operation === 'cancel') void review(p, true).catch(() => {}); else setEditing(p.id); }}>Xem và duyệt</button>
          </div>
        )}
      </article>)}
    </section>}

    <section className="sw-ci-section sw-ci-history-chat">
      <h3>Hỏi AI về lịch sử hội thoại này{(state?.chat || []).length > 0 ? <span>({state.chat.length})</span> : null}</h3>
      {!state?.analysis_id && <p className="sw-secondary">Cần phân tích hội thoại trước để bật hỏi đáp theo bằng chứng.</p>}
      <div aria-live="polite">{(state?.chat || []).map((turn, index) => <article className="sw-ci-chat-turn" key={index}>
        <small>Phiên {turn.analysis_id.slice(0, 8)} · {displayDateTime(turn.created_at)}{turn.analysis_id !== state.analysis_id && ' · Phiên trước'}</small>
        <p><strong>{turn.query}</strong></p>
        <p>{turn.answer}</p>
        {turn.evidence?.map((e, i) => <HistoricalSource key={i} customerId={customer.customerId} analysisId={turn.analysis_id} evidence={e} />)}
      </article>)}</div>
      <form className="sw-ci-composer-form" onSubmit={submitQuestion}>
        <div className="sw-composer-box">
          <textarea
            aria-label={`Hỏi AI về lịch sử của ${customer.name}`}
            placeholder="Hỏi AI về nội dung khách đã trao đổi..."
            rows={1}
            maxLength={4000}
            value={query}
            disabled={!state?.analysis_id || busy}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void submitQuestion(event);
              }
            }}
          />
          <div className="sw-composer-tools">
            <button
              className="sw-primary-button sw-send-button"
              type="submit"
              aria-label={busy ? 'Đang gửi câu hỏi' : 'Gửi câu hỏi'}
              disabled={!state?.analysis_id || !query.trim() || busy}
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      </form>
    </section>
  </div>;
}

