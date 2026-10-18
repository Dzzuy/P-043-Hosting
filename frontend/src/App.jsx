import { useState, useEffect } from 'react';
import { Header } from './components/layout/Header';
import { NotificationDrawer } from './components/layout/NotificationDrawer';
import { CopilotView } from './components/copilot/CopilotView';
import { RoleplayView } from './components/roleplay/RoleplayView';
import { KnowledgeView } from './components/knowledge/KnowledgeView';
import { LoginView } from './components/auth/LoginView';
import { ChangePasswordView } from './components/auth/ChangePasswordView';
import { ManagerReviewView } from './components/manager/ManagerReviewView';

import { authApi } from './api/authApi';
import { practiceApi } from './api/practiceApi';

export function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authStatus, setAuthStatus] = useState('loading');
  const [currentTab, setCurrentTab] = useState('copilot');
  const [scenarios, setScenarios] = useState([]);
  const [scenarioStatus, setScenarioStatus] = useState('loading');
  const [scenarioReloadToken, setScenarioReloadToken] = useState(0);
  const [sourceDocumentId, setSourceDocumentId] = useState(null);
  const [sourceReference, setSourceReference] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [isNotifOpen, setIsNotifOpen] = useState(false);
  const [copilotQuery, setCopilotQuery] = useState('');
  const [copilotOpened, setCopilotOpened] = useState(false);

  useEffect(() => {
    async function restoreSession() {
      try {
        const user = await authApi.me();
        setCurrentUser(user);
        if (user.role === 'advisor') {
          setCurrentTab('copilot');
          setCopilotOpened(true);
        }
        setAuthStatus('authenticated');
      } catch {
        setCurrentUser(null);
        setAuthStatus('anonymous');
      }
    }
    restoreSession();
  }, []);

  // Fetch real scenarios only after an advisor is authenticated.
  useEffect(() => {
    if (authStatus !== 'authenticated' || currentUser?.role !== 'advisor') return;
    async function loadBackendScenarios() {
      try {
        const backendList = await practiceApi.getScenarios();
        if (!Array.isArray(backendList)) throw new Error('Danh sách tình huống không hợp lệ.');
        setScenarios(backendList.map((scenario) => {
          const model = scenario.title.match(/VF\s*[3-9]/i)?.[0].replace(/\s+/, ' ') || 'VinFast';
          return {
            ...scenario,
            model,
            model_badge: model,
            difficulty: { Easy: 'Cơ bản', Medium: 'Tiêu chuẩn', Hard: 'Nâng cao' }[scenario.difficulty] || scenario.difficulty,
          };
        }));
        setScenarioStatus('ready');
      } catch {
        setScenarios([]);
        setScenarioStatus('error');
      }
    }
    loadBackendScenarios();
  }, [authStatus, currentUser?.role, scenarioReloadToken]);

  const handleLogin = async (username, password) => {
    const user = await authApi.login(username, password);
    setCurrentUser(user);
    setAuthStatus('authenticated');
    if (user.role === 'advisor') {
      setCurrentTab('copilot');
      setCopilotOpened(true);
    } else {
      setCurrentTab('manager');
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } finally {
      setCurrentUser(null);
      setAuthStatus('anonymous');
      setCurrentTab('copilot');
      setScenarios([]);
      setScenarioStatus('loading');
      setCopilotOpened(false);
      setCopilotQuery('');
    }
  };

  const handleChangePassword = async (currentPassword, newPassword) => {
    await authApi.changePassword(currentPassword, newPassword);
    setCurrentUser(null);
    setAuthStatus('anonymous');
  };

  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleMarkAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const handleSelectNotification = (item) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === item.id ? { ...n, read: true } : n))
    );
    if (item.link) {
      setCurrentTab(item.link);
      if (item.link === 'copilot') setCopilotOpened(true);
    }
  };

  if (authStatus === 'loading') {
    return <div className="auth-loading" role="status">Đang kiểm tra phiên đăng nhập…</div>;
  }

  if (authStatus === 'anonymous') {
    return <LoginView onLogin={handleLogin} />;
  }

  if (currentUser?.must_change_password) {
    return <ChangePasswordView username={currentUser.username}
      onChangePassword={handleChangePassword} onLogout={handleLogout} />;
  }

  if (currentUser?.role === 'manager') {
    return (
      <ManagerReviewView
        currentUser={currentUser}
        onLogout={handleLogout}
      />
    );
  }

  const advisorProfile = {
    name: currentUser.display_name,
    username: currentUser.username,
    role: 'Tư vấn viên',
  };

  return (
    <div className={`app-container${currentTab === 'copilot' ? ' copilot-app-container' : ''}${currentTab === 'knowledge' ? ' knowledge-app-container' : ''}${currentTab === 'roleplay' ? ' roleplay-app-container' : ''}`}>
      {/* GLOBAL TOP HEADER */}
      <Header
        currentTab={currentTab}
        onTabChange={(tab) => {
          setCurrentTab(tab);
          if (tab === 'copilot') setCopilotOpened(true);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
        unreadCount={unreadCount}
        hasNotifications={notifications.length > 0}
        onOpenNotifications={() => setIsNotifOpen(true)}
        advisorProfile={advisorProfile}
        onLogout={handleLogout}
      />

      {/* MAIN CONTENT AREA */}
      <main className={`main-content${currentTab === 'copilot' ? ' copilot-main-content' : ''}${currentTab === 'knowledge' ? ' knowledge-main-content' : ''}`}>
        {(currentTab === 'copilot' || copilotOpened) && (
          <div style={{ display: currentTab === 'copilot' ? 'flex' : 'none', flex: 1, minHeight: 0, height: '100%', flexDirection: 'column' }}>
          <CopilotView
            currentUser={currentUser}
            initialQuery={copilotQuery}
            onOpenDocument={(documentId, reference = null) => {
              setSourceDocumentId(documentId);
              setSourceReference(reference);
              setCurrentTab('knowledge');
            }}
          />
          </div>
        )}

        {currentTab === 'roleplay' && (
          <RoleplayView
            onOpenKnowledge={() => {
              setSourceDocumentId(null);
              setSourceReference(null);
              setCurrentTab('knowledge');
            }}
            scenarios={scenarios}
            scenarioStatus={scenarioStatus}
            onRetryScenarios={() => {
              setScenarioStatus('loading');
              setScenarioReloadToken((value) => value + 1);
            }}
          />
        )}

        {currentTab === 'knowledge' && (
          <KnowledgeView
            sourceDocumentId={sourceDocumentId}
            sourceReference={sourceReference}
          />
        )}

      </main>

      {/* NOTIFICATIONS FLYOUT */}
      <NotificationDrawer
        isOpen={isNotifOpen}
        onClose={() => setIsNotifOpen(false)}
        notifications={notifications}
        onMarkAllRead={handleMarkAllRead}
        onSelectNotification={handleSelectNotification}
      />
    </div>
  );
}

export default App;
