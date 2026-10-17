import { BookIcon, BellIcon, LogoutIcon } from '../common/Icons';
import { CopilotLogo } from '../common/CopilotLogo';

export function Header({
  currentTab,
  onTabChange,
  unreadCount = 0,
  onOpenNotifications,
  advisorProfile,
  onLogout,
}) {
  const tabs = [
    { id: 'home', label: 'Trang chủ', icon: <span className="header-home-icon" aria-hidden="true">⌂</span> },
    { id: 'copilot', label: 'Trợ lý Copilot', icon: <CopilotLogo style={{ width: 18, height: 18 }} /> },
    { id: 'roleplay', label: 'Thực chiến', icon: <span className="roleplay-file-icon" aria-hidden="true" /> },
    { id: 'knowledge', label: 'Kho kiến thức', icon: <BookIcon style={{ width: 18, height: 18 }} /> },
  ];

  return (
    <header className="top-header">
      <div className="top-header-inner">
        {/* BRAND LOGO */}
        <button className="brand-section" type="button" onClick={() => onTabChange('home')}>
          <span className="header-brand-logo"><img src="/vinfast-official-logo.png?v=silver" alt="VinFast" /></span>
          <div className="brand-info">
            <span className="brand-title">AI Sales Coach &amp; Co-pilot</span>
            <span className="brand-subtitle">Nền tảng đào tạo và hỗ trợ tư vấn bán hàng ô tô</span>
          </div>
        </button>

        {/* NAVIGATION PILL TABS (DESKTOP) */}
        <nav className="nav-tabs-pill desktop-nav-pill" aria-label="Main Navigation">
          {tabs.map((tab) => {
            const isActive = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                className={`nav-tab-item ${isActive ? 'active' : ''}`}
                onClick={() => onTabChange(tab.id)}
                aria-current={isActive ? 'page' : undefined}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>

        {/* HEADER ACTIONS */}
        <div className="header-actions">
          {/* Notifications button */}
          <button
            className="icon-badge-btn"
            onClick={onOpenNotifications}
            aria-label="Thông báo"
            title="Thông báo"
          >
            <BellIcon style={{ width: 16, height: 16 }} />
            {unreadCount > 0 && <span className="notif-badge-pill">{unreadCount}</span>}
          </button>

          <div className="user-profile-badge">

              <span className="header-user-avatar" aria-hidden="true">{advisorProfile.name.trim().charAt(0)}</span>
              <div className="user-details">
                <span className="user-name">{advisorProfile.name}</span>
                <span className="user-role">{advisorProfile.role}</span>
              </div>

          </div>
          <button className="header-logout-btn" type="button" onClick={onLogout}>
            <LogoutIcon style={{ width: 17, height: 17 }} />
            Đăng xuất
          </button>
        </div>
      </div>

      {/* MOBILE NAV PILLS BAR */}
      <nav className="mobile-nav-pills" aria-label="Mobile Navigation">
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              className={`mobile-nav-pill-item ${isActive ? 'active' : ''}`}
              onClick={() => onTabChange(tab.id)}
              aria-current={isActive ? 'page' : undefined}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </header>
  );
}
