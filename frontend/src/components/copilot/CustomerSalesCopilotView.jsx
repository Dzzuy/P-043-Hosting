import { useEffect, useRef, useState } from 'react';
import { UsersRound, Info, ArrowLeft, X, MessageSquare } from 'lucide-react';
import { createId } from '../../lib/id';
import { CustomerList } from './customerWorkspace/CustomerList';
import { ConversationWorkspace } from './customerWorkspace/ConversationWorkspace';
import { CustomerToolsDrawer } from './customerWorkspace/CustomerToolsDrawer';
import { IconButton } from './customerWorkspace/WorkspacePrimitives';
import { appendDraft, filterCustomers } from './customerWorkspace/workspaceData';
import { useCustomerWorkspace } from './customerWorkspace/useCustomerWorkspace';
import { useWorkspaceStorage } from './customerWorkspace/workspaceStorage';
import './customerWorkspace/customerWorkspace.css';

export function CustomerSalesCopilotView({ currentUser, active = true, navigationIntent }) {
  const workspace = useCustomerWorkspace(currentUser, active);
  const { customers, selectedId, draftEnabled } = workspace;
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const storage = useWorkspaceStorage(currentUser?.user_id);
  const { drafts, starred } = storage;
  const [highlight, setHighlight] = useState(null);
  const [creatingTask, setCreatingTask] = useState(false);
  const [drawer, setDrawer] = useState(null);
  const [mobileView, setMobileView] = useState('list');
  const [draftOpen, setDraftOpen] = useState(false);
  const [toast, setToast] = useState('');
  const composerRef = useRef(null);
  const intentRef = useRef(null);
  const selectedRef = useRef(selectedId);
  useEffect(() => { selectedRef.current = selectedId; }, [selectedId]);
  const found = filterCustomers(customers, query, filter).find((item) => item.id === selectedId);
  const customer = found ? { ...found, starred: Boolean(starred[selectedId]) } : null;

  useEffect(() => {
    if (!navigationIntent || intentRef.current === navigationIntent || !customers.some((item) => item.id === navigationIntent.conversationId)) return;
    intentRef.current = navigationIntent;
    workspace.selectCustomer(navigationIntent.conversationId);
    setQuery(''); setFilter('all'); setDrawer(navigationIntent.tool || null);
    setCreatingTask(false); setDraftOpen(false); setMobileView('conversation');
    setHighlight(navigationIntent.taskId ? { taskId: navigationIntent.taskId, nonce: navigationIntent.nonce } : null);
  }, [navigationIntent, customers, workspace]);

  useEffect(() => { if (highlight && !highlight.taskId) { const timer = setTimeout(() => setHighlight(null), 3500); return () => clearTimeout(timer); } }, [highlight]);
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(''), 4000); return () => clearTimeout(timer); } }, [toast]);

  function selectCustomer(id) {
    workspace.selectCustomer(id); setHighlight(null);
    setDrawer((previous) => previous === 'copilot' ? previous : null); setDraftOpen(false); setCreatingTask(false); setMobileView('conversation');
  }
  function openDraft() { setDrawer(null); setDraftOpen(true); setMobileView('conversation'); }
  function showTool(type) {
    setDrawer(type); setDraftOpen(false); setCreatingTask(false);
    if (type === 'copilot') void workspace.loadKnowledge().catch(() => {});
  }
  async function insertDraft(mode) {
    if (!customer?.draft || !draftEnabled || customer.draftStale) return;
    if (mode === 'copy') {
      try { await navigator.clipboard.writeText(customer.draft); setToast('Đã sao chép bản nháp. Nội dung đang soạn được giữ nguyên.'); }
      catch { setToast('Trình duyệt chưa cho phép sao chép. Chọn nội dung bản nháp để sao chép thủ công.'); }
      return;
    }
    const content = mode === 'append' ? appendDraft(drafts[selectedId] || '', customer.draft) : customer.draft;
    if (content.length > 6000) { setToast('Nội dung vượt 6.000 ký tự. Rút gọn ô soạn tin rồi thử lại.'); return; }
    storage.update('drafts', selectedId, content);
    setDraftOpen(false); setToast('Đã đưa bản nháp vào ô soạn. Chưa lưu thành tin nhắn.');
    requestAnimationFrame(() => composerRef.current?.focus());
  }
  async function sendMessage() {
    const id = selectedId;
    const content = (drafts[id] || '').trim();
    if (!content || workspace.sending || !customer?.loaded) return;
    try {
      const message = await workspace.sendMessage(id, content);
      if (message) {
        storage.update('drafts', id, (previous) => previous?.trim() === content ? '' : previous);
        if (selectedRef.current === id) { setHighlight(null); setToast('Đã lưu tin nhắn vào hội thoại trong hệ thống.'); }
      }
    } catch (error) { setToast(`Chưa lưu được tin nhắn: ${error.message}`); }
  }
  async function showSource(messageId) {
    const id = selectedId;
    try {
      await workspace.ensureSource(id, messageId);
      if (selectedRef.current !== id) return;
      setMobileView('conversation'); setDrawer(null);
      setHighlight({ messageId, nonce: createId('highlight') });
    } catch (error) { setToast(error.message); }
  }
  function openTasksDialog() { setDrawer('tasks'); setDraftOpen(false); setCreatingTask(true); }
  async function createTask(task) {
    const id = selectedId;
    await workspace.createTask(id, task);
    if (selectedRef.current === id) { setCreatingTask(false); setToast('Đã lưu công việc / lịch hẹn.'); }
  }
  async function runAction(action) {
    try { await action(); } catch (error) { setToast(error.message || 'Thao tác chưa thành công. Vui lòng thử lại.'); }
  }
  async function saveStage(stage, reason) {
    const id = selectedId;
    await workspace.updateStage(id, stage, reason);
    if (selectedRef.current === id) { setToast(stage ? 'Đã lưu giai đoạn sales chọn.' : 'Đã dùng lại giai đoạn AI đề xuất.'); }
  }

  return <div className={`sales-workspace sw-focused-workspace ${mobileView === 'conversation' ? 'sw-show-conversation' : 'sw-show-list'} ${drawer && (customer || drawer === 'copilot') ? 'sw-has-drawer' : ''}`}>
    <div className="sw-workspace-body">
      <CustomerList customers={customers} selectedId={selectedId} onSelect={selectCustomer} query={query} onQueryChange={setQuery} filter={filter} onFilterChange={setFilter} status={workspace.listStatus} error={workspace.listError} onRetry={workspace.loadList} onOpenCopilot={() => showTool('copilot')} />
      {customer ? <ConversationWorkspace key={selectedId} customer={customer} activeTool={drawer}
        onStar={() => storage.update('starred', selectedId, !starred[selectedId])}
        onCreateTask={openTasksDialog} highlight={highlight}
        composerValue={drafts[selectedId] || ''} onComposerChange={(value) => storage.update('drafts', selectedId, value)}
        onSend={sendMessage} sending={workspace.sending} loading={workspace.loadingDetail || !customer.loaded}
        error={workspace.detailError} onRetry={() => workspace.loadDetails(selectedId, true)} composerRef={composerRef}
        onBack={() => { if (drawer) setDrawer(null); else setMobileView('list'); }} onShowTool={showTool} onRefresh={() => runAction(() => workspace.refresh(selectedId))}
        onLoadOlder={(beforeSeq) => runAction(() => workspace.loadMessages(selectedId, { beforeSeq }))} loadingOlder={workspace.loadingOlder}
        onSaveStage={saveStage} stageBusy={workspace.stageBusy}
        draftOpen={draftOpen} onOpenDraft={openDraft} onCloseDraft={() => setDraftOpen(false)}
        draftEnabled={draftEnabled} onToggleDraft={() => runAction(workspace.toggleDraft)} preferenceBusy={workspace.preferenceBusy}
        onGenerateDraft={() => runAction(() => workspace.generateDraft(selectedId))} draftBusy={workspace.draftBusy} onInsertDraft={insertDraft}
      /> : <section className="sw-conversation"><div className="sw-empty"><MessageSquare size={32} /><strong>Không gian tư vấn khách hàng</strong><p>{workspace.listStatus === 'loading' ? 'Đang tải danh sách khách hàng…' : 'Chọn một khách hàng để xem hội thoại.'}</p></div></section>}
    {drawer && (customer || drawer === 'copilot') && <CustomerToolsDrawer key={drawer === 'copilot' ? 'copilot' : `${selectedId}-${drawer}`} type={drawer} customer={customer} onClose={() => setDrawer(null)} onSourceClick={showSource}
      onAnalyze={() => runAction(() => workspace.analyze(selectedId))} analyzing={workspace.analyzing} analysisChanges={workspace.analysisChanges} onShowTool={showTool}
      onToggleTask={(taskId) => runAction(() => workspace.toggleTask(selectedId, customer.tasks.find((task) => task.id === taskId)))}
      creatingTask={creatingTask} onCancelCreate={() => setCreatingTask(false)} onCreate={createTask} onCreateTask={openTasksDialog} taskBusy={workspace.taskBusy} onSaveStage={saveStage} stageBusy={workspace.stageBusy}
      highlightedTaskId={highlight?.taskId} ownerId={currentUser?.user_id} onEditTask={(taskId, changes) => workspace.editTask(selectedId, taskId, changes)} onConfirmFact={(field, value) => workspace.confirmFact(selectedId, field, value)}
      knowledge={workspace.knowledge} onLoadHistory={workspace.loadKnowledge} onQueryChange={workspace.setKnowledgeQuery}
      onSearch={workspace.searchKnowledge}
    />}
    </div>
    <div className="sw-mobile-switcher"><button type="button" className={mobileView === 'list' ? 'is-active' : ''} onClick={() => { setDrawer(null); setMobileView('list'); }}><UsersRound size={16} />Khách hàng</button><button type="button" className={mobileView === 'conversation' ? 'is-active' : ''} disabled={!customer} onClick={() => { setDrawer(null); setMobileView('conversation'); }}><ArrowLeft size={16} />Hội thoại</button></div>
    {storage.error && <div className="sw-error-banner" role="alert">{storage.error}</div>}
    <div className={`sw-toast ${toast ? 'is-visible' : ''}`} role="status" aria-live="polite">{toast && <><Info size={16} /><span>{toast}</span><IconButton label="Ẩn thông báo" onClick={() => setToast('')}><X size={14} /></IconButton></>}</div>
  </div>;
}
