import { useEffect, useId, useRef } from 'react';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import './modeChooser.css';

export function ModeChooserDialog({ onClose, onChoose }) {
  const { ref, onKeyDown } = useDialogFocus(onClose);
  const textButton = useRef(null);
  const headingId = useId();

  useEffect(() => {
    textButton.current?.focus();
  }, []);

  return (
    <div className="mode-chooser-backdrop">
      <section className="mode-chooser" role="dialog" aria-modal="true" aria-labelledby={headingId} ref={ref} tabIndex={-1} onKeyDown={onKeyDown}>
        <h2 id={headingId}>Bạn muốn luyện thế nào?</h2>
        <div className="mode-chooser-options">
          <button ref={textButton} type="button" className="mode-chooser-option" onClick={() => onChoose('text')}>
            <span className="mode-chooser-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" /></svg></span>
            <strong>Nhắn tin</strong>
          </button>
          <button type="button" className="mode-chooser-option mode-chooser-option-voice" onClick={() => onChoose('voice')}>
            <span className="mode-chooser-new">Mới!</span>
            <span className="mode-chooser-icon voice"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" /></svg></span>
            <strong>Gọi thoại</strong>
          </button>
        </div>
        <p>Có thể đổi chế độ bất cứ lúc nào.</p>
        <button type="button" className="mode-chooser-cancel" onClick={onClose}>Hủy</button>
      </section>
    </div>
  );
}
