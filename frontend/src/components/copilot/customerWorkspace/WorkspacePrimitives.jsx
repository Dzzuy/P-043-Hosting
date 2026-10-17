import { useEffect, useRef } from 'react';
import { X, Sparkles } from 'lucide-react';

export function Avatar({ customer, size = '', sales = false }) {
  return <span className={`sw-avatar ${sales ? 'sw-avatar-sales' : `sw-avatar-${customer?.color || 'blue'}`} ${size ? `sw-avatar-${size}` : ''}`} aria-hidden="true">{sales ? 'TV' : customer?.initials}</span>;
}

export function StageBadge({ customer }) {
  return <span className={`sw-badge sw-badge-${customer.tone}`}><span className="sw-badge-dot" />{customer.stage}</span>;
}

export function IconButton({ label, children, className = '', ...props }) {
  return <button type="button" className={`sw-icon-button ${className}`} aria-label={label} title={label} {...props}>{children}</button>;
}

export function CopilotBubble({ onOpen }) {
  return <div className="sw-copilot-dock"><button type="button" className="sw-copilot-bubble" title="Hỏi Copilot về kiến thức xe" aria-label="Hỏi Copilot" aria-expanded={false} onClick={onOpen}><Sparkles size={18} /><span>Hỏi Copilot</span></button></div>;
}

export function IntelligenceCard({ icon: Icon = Sparkles, title, action, children, className = '' }) {
  return <section className={`sw-intelligence-card ${className}`}>
    <div className="sw-card-heading"><h3><Icon size={16} strokeWidth={1.8} />{title}</h3>{action}</div>
    {children}
  </section>;
}

export function DetailDialog({ title, children, onClose, footer, variant = 'dialog' }) {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = dialogRef.current;
    const selector = 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]';
    (dialog.querySelector('[autofocus]') || dialog.querySelector(selector))?.focus();
    function onKeyDown(event) {
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); }
      if (event.key === 'Tab') {
        const targets = [...dialog.querySelectorAll(selector)];
        const first = targets[0]; const last = targets.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    dialog.addEventListener('keydown', onKeyDown);
    return () => { dialog.removeEventListener('keydown', onKeyDown); previous?.focus(); };
  }, []);
  return <div className={`sw-dialog-backdrop ${variant === 'drawer' ? 'sw-drawer-backdrop' : ''}`} onClick={onClose}>
    <section ref={dialogRef} className={`sw-dialog ${variant === 'drawer' ? 'sw-tool-drawer' : ''}`} role="dialog" aria-modal="true" aria-labelledby="sw-detail-dialog-title" onClick={(event) => event.stopPropagation()}>
      <div className="sw-dialog-heading"><h2 id="sw-detail-dialog-title">{title}</h2><IconButton label="Đóng cửa sổ" onClick={onClose}><X size={19} /></IconButton></div>
      <div className="sw-dialog-body">{children}</div>
      {footer && <div className="sw-dialog-footer">{footer}</div>}
    </section>
  </div>;
}

/** Desktop panels share the grid; narrow screens use one modal layer. */
export function ContextDrawerHost({ title, children, onClose }) {
  const panelRef = useRef(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement;
    const panel = panelRef.current;
    const query = 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]';
    panel.querySelector(query)?.focus();
    const media = window.matchMedia(panel.closest('.copilot-shell') ? '(max-width: 1439px)' : '(max-width: 1199px)');
    const workspace = panel.closest('.sw-workspace-body');
    let modal = false;
    function syncModal() {
      modal = media.matches || workspace.getBoundingClientRect().width < 1100;
      panel.setAttribute('aria-modal', String(modal));
      panel.parentElement.classList.toggle('is-overlay', modal);
      for (const child of workspace.children) if (child !== panel.parentElement) child.inert = modal;
    }
    syncModal(); media.addEventListener('change', syncModal);
    const observer = new ResizeObserver(syncModal); observer.observe(workspace);
    function keys(event) {
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current(); }
      if (event.key === 'Tab' && modal) {
        const targets = [...panel.querySelectorAll(query)].filter((node) => node.getClientRects().length);
        const first = targets[0]; const last = targets.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', keys);
    return () => {
      observer.disconnect(); document.removeEventListener('keydown', keys); media.removeEventListener('change', syncModal);
      for (const child of workspace.children) child.inert = false;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return <div className="sw-context-drawer-host" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={panelRef} className="sw-tool-drawer sw-context-drawer" role="dialog" aria-labelledby="sw-context-title">
      <div className="sw-dialog-heading"><div><h2 id="sw-context-title">{title}</h2>{title === 'Trợ lý Copilot' && <small>Kiến thức xe · Không gửi cho khách</small>}</div><IconButton label="Đóng cửa sổ" onClick={onClose}><X size={19} /></IconButton></div>
      <div className="sw-dialog-body">{children}</div>
    </section>
  </div>;
}
