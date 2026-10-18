import { useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, LogoutIcon } from '../common/Icons';
import './accountMenu.css';

// Shared by the advisor and manager top bars: the avatar opens a small account card.
export function AccountMenu({ name, username, roleLabel, onLogout }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const cardId = useId();
  const displayName = name?.trim() || roleLabel;

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="account-menu" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`account-menu-trigger ${open ? 'is-open' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? cardId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="header-user-avatar" aria-hidden="true">{displayName.charAt(0)}</span>
        <span className="user-details">
          <span className="user-name">{displayName}</span>
          <span className="user-role">{roleLabel}</span>
        </span>
        <ChevronDown className="account-menu-chevron" aria-hidden="true" />
      </button>

      {open && (
        <div id={cardId} className="account-menu-card" role="dialog" aria-label="Tài khoản">
          <div className="account-menu-identity">
            <span className="account-menu-avatar" aria-hidden="true">{displayName.charAt(0)}</span>
            <span className="account-menu-names">
              <strong>{displayName}</strong>
              {username && <span>{username}</span>}
            </span>
          </div>
          <dl className="account-menu-facts">
            <dt>Vai trò</dt>
            <dd>{roleLabel}</dd>
          </dl>
          <button type="button" className="account-menu-logout" onClick={onLogout}>
            <LogoutIcon aria-hidden="true" />
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
