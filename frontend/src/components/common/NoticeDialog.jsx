import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import './NoticeDialog.css';

export function NoticeDialog({ notice, onAction, onClose }) {
  const id = useId();
  const card = useRef(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  const open = Boolean(notice);
  const dismissible = notice?.dismissible;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    card.current?.querySelector('button[data-primary="true"]')?.focus();
    const keydown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (dismissible) closeRef.current?.();
      }
      if (event.key !== 'Tab') return;
      const buttons = [...card.current.querySelectorAll('button:not(:disabled)')];
      const first = buttons[0];
      const last = buttons.at(-1);
      if (event.shiftKey && (document.activeElement === first || !card.current.contains(document.activeElement))) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !card.current.contains(document.activeElement))) {
        event.preventDefault(); first?.focus();
      }
    };
    document.addEventListener('keydown', keydown, true);
    return () => {
      document.removeEventListener('keydown', keydown, true);
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, [open, dismissible]);
  if (!notice) return null;
  return createPortal(
    <div className="notice-dialog-backdrop" onClick={(event) => { if (event.target === event.currentTarget && dismissible) onClose?.(); }}>
      <section ref={card} className={`notice-dialog notice-dialog-${notice.tone || 'info'}`} role="alertdialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={notice.message ? `${id}-message` : undefined}>
        <div className="notice-dialog-icon" aria-hidden="true">{{ info: 'i', success: '✓', warning: '!', error: '!' }[notice.tone] || 'i'}</div>
        <h2 id={`${id}-title`}>{notice.title}</h2>
        {notice.message && <p id={`${id}-message`}>{notice.message}</p>}
        <div className="notice-dialog-actions">{notice.actions.map((action) => <button key={action.id} type="button" data-primary={action.kind === 'primary'} className={`notice-dialog-action notice-dialog-action-${action.kind}`} onClick={() => onAction(action.id)}>{action.label}</button>)}</div>
      </section>
    </div>, document.body,
  );
}
