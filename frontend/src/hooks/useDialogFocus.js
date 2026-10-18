import { useCallback, useEffect, useRef } from 'react';

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Drawer/dialog behaviour: focus moves in on mount, Tab is trapped, Esc closes,
 * body scroll is locked, and focus returns to the opener on unmount.
 */
export function useDialogFocus(onClose) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const opener = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  const onKeyDown = useCallback((event) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      closeRef.current?.();
      return;
    }
    if (event.key !== 'Tab' || !ref.current) return;
    const items = [...ref.current.querySelectorAll(FOCUSABLE)].filter((node) => node.offsetParent !== null);
    if (items.length === 0) {
      event.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === ref.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }, []);

  return { ref, onKeyDown };
}
