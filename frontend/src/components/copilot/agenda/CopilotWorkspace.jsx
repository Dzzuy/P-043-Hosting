import { useEffect, useState } from 'react';
import { CalendarDays, LayoutDashboard, UsersRound } from 'lucide-react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { CustomerSalesCopilotView } from '../CustomerSalesCopilotView';
import { CreateTaskDialog, TaskEditor } from '../customerWorkspace/CreateTaskDialog';
import { DetailDialog } from '../customerWorkspace/WorkspacePrimitives';
import { DashboardView } from './DashboardView';
import { CalendarView } from './CalendarView';
import { dateKey, mondayOf } from './agendaData';
import { CHANGE_EVENT } from './agendaResource';
import './agenda.css';

const pages = [['dashboard', 'Dashboard', LayoutDashboard], ['customers', 'Khách hàng', UsersRound], ['calendar', 'Lịch sự kiện', CalendarDays]];
export function CopilotWorkspace({ currentUser }) {
  const [page, setPage] = useState('dashboard'); const [customerOpened, setCustomerOpened] = useState(false);
  const [calendarOpened, setCalendarOpened] = useState(false); const [intent, setIntent] = useState(null);
  const [calendarWeek, setCalendarWeek] = useState(() => mondayOf()); const [createCustomers, setCreateCustomers] = useState(null);
  const [editing, setEditing] = useState(null); const [focusedTask, setFocusedTask] = useState(null);
  useEffect(() => {
    const clearStaleFocus = () => setFocusedTask(null);
    window.addEventListener(CHANGE_EVENT, clearStaleFocus);
    return () => window.removeEventListener(CHANGE_EVENT, clearStaleFocus);
  }, []);
  function navigate(value) { if (value === 'customers') setCustomerOpened(true); if (value === 'calendar') setCalendarOpened(true); setPage(value); }
  function openCustomer(item) { if (!item.conversation_id) return; setIntent({ conversationId: item.conversation_id, tool: item.tool || (item.id ? 'tasks' : null), taskId: item.id, nonce: Date.now() }); navigate('customers'); }
  function openCalendar(value) { setCalendarWeek(mondayOf(value ? dateKey(value) : dateKey())); navigate('calendar'); }
  return <div className="copilot-shell"><nav className="copilot-sidebar" aria-label="Các trang Trợ lý Copilot"><span className="copilot-sidebar-title">KHÔNG GIAN CỦA BẠN</span>{pages.map(([id, label, Icon]) => <button type="button" key={id} title={label} aria-current={page === id ? 'page' : undefined} className={page === id ? 'is-active' : ''} onClick={() => navigate(id)}><Icon size={19} /><span>{label}</span></button>)}<p>Chăm sóc khách hàng<br />và quản lý lịch cá nhân.</p></nav>
    <main className="copilot-pages"><div className="copilot-subpage" hidden={page !== 'dashboard'}><DashboardView currentUser={currentUser} active={page === 'dashboard'} onCreate={setCreateCustomers} onEdit={setEditing} onCustomer={openCustomer} onCalendar={openCalendar} focusedTask={focusedTask} onClearFocus={() => setFocusedTask(null)} /></div>
      {customerOpened && <div className="copilot-subpage copilot-customers" hidden={page !== 'customers'}><CustomerSalesCopilotView currentUser={currentUser} active={page === 'customers'} navigationIntent={intent} /></div>}
      {calendarOpened && <div className="copilot-subpage" hidden={page !== 'calendar'}><CalendarView currentUser={currentUser} active={page === 'calendar'} week={calendarWeek} onWeekChange={setCalendarWeek} onCustomer={openCustomer} onTask={(item) => { setFocusedTask(item); navigate('dashboard'); }} /></div>}
    </main>
    {createCustomers && <CreateTaskDialog customers={createCustomers} onClose={() => setCreateCustomers(null)} onCreate={async (values) => { await salesCopilotApi.createPersonalTask(values); setCreateCustomers(null); }} />}
    {editing && <DetailDialog title="Công việc / lịch hẹn" onClose={() => setEditing(null)}><TaskEditor key={editing.id} task={editing} onCancel={() => setEditing(null)} onSave={async (values) => { await salesCopilotApi.editTask(editing.id, values); setEditing(null); }} /></DetailDialog>}
  </div>;
}
