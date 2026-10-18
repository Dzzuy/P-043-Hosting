import "./managerShell.css";
import {
  DashboardIcon,
  CheckCircleIcon,
  ClipboardIcon,
  UsersIcon,
} from "../common/Icons";
import { AccountMenu } from "./AccountMenu";

// Same markup and classes as the advisor Header, so both portals share one top bar.
export function ManagerTopNav({
  activeTab,
  onTabChange,
  currentUser,
  pendingCount = 0,
  onLogout,
}) {
  const menuItems = [
    { id: "dashboard", label: "Tổng quan", icon: DashboardIcon },
    { id: "assignments", label: "Giao bài", icon: ClipboardIcon },
    { id: "reports", label: "Lịch sử luyện tập", icon: CheckCircleIcon, badge: pendingCount > 0 ? pendingCount : null },
    { id: "accounts", label: "Tài khoản", icon: UsersIcon },
  ];

  const displayName = currentUser?.display_name?.trim() || "Quản lý";

  const renderItem = (item, className) => {
    const Icon = item.icon;
    const isActive = activeTab === item.id;
    return (
      <button
        key={item.id}
        type="button"
        className={`${className} ${isActive ? "active" : ""}`}
        onClick={() => onTabChange(item.id)}
        aria-current={isActive ? "page" : undefined}
      >
        <Icon style={{ width: 18, height: 18 }} />
        <span>{item.label}</span>
        {item.badge && (
          <span className="nav-tab-badge" aria-label={`${item.badge} bài chờ duyệt`}>
            {item.badge}
          </span>
        )}
      </button>
    );
  };

  return (
    <header className="top-header">
      <div className="top-header-inner">
        <button className="brand-section" type="button" onClick={() => onTabChange("dashboard")}>
          <span className="header-brand-logo"><img src="/vinfast-official-logo.png?v=silver" alt="VinFast" /></span>
          <div className="brand-info">
            <span className="brand-title">AI Sales Coach &amp; Co-pilot</span>
            <span className="brand-subtitle">Nền tảng đào tạo và hỗ trợ tư vấn bán hàng ô tô</span>
          </div>
        </button>

        <nav className="nav-tabs-pill desktop-nav-pill" aria-label="Điều hướng quản lý">
          {menuItems.map((item) => renderItem(item, "nav-tab-item"))}
        </nav>

        <div className="header-actions">
          <AccountMenu
            name={displayName}
            username={currentUser?.username}
            roleLabel="Quản lý"
            onLogout={onLogout}
          />
        </div>
      </div>

      <nav className="mobile-nav-pills" aria-label="Điều hướng quản lý (di động)">
        {menuItems.map((item) => renderItem(item, "mobile-nav-pill-item"))}
      </nav>
    </header>
  );
}
