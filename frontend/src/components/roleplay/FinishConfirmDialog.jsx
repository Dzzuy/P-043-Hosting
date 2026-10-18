import { useEffect, useRef } from 'react';
import { CloseIcon } from '../common/Icons';
import './roleplayFinish.css';

export function FinishConfirmDialog({ isOpen, onClose, onConfirm, finishing }) {
  const cancelRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    cancelRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !finishing) onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen, finishing, onClose]);

  if (!isOpen) return null;

  return (
    <div className="practice-finish-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !finishing) onClose();
    }}>
      <section className="practice-finish-dialog" role="dialog" aria-modal="true" aria-labelledby="practice-finish-title" aria-describedby="practice-finish-description">
        <button type="button" className="practice-finish-close" onClick={onClose} disabled={finishing} aria-label="Đóng">
          <CloseIcon aria-hidden="true" />
        </button>
        <div className="practice-finish-main">
          <div className="practice-finish-art" aria-hidden="true">
            <svg viewBox="0 0 88 88" fill="none">
              <path d="M24 12h27l15 15v39a6 6 0 0 1-6 6H24a6 6 0 0 1-6-6V18a6 6 0 0 1 6-6Z" stroke="#5A9AF8" strokeWidth="3" />
              <path d="M51 12v15h15M29 38h25M29 47h18M29 56h13" stroke="#5A9AF8" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="62" cy="60" r="15" fill="#2078EB" />
              <path d="m55 60 5 5 9-10" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <h2 id="practice-finish-title">{finishing ? 'Đang chấm điểm phiên luyện tập' : 'Xác nhận hoàn tất phiên luyện tập'}</h2>
            <p id="practice-finish-description" role={finishing ? 'status' : undefined}>{finishing ? 'Hệ thống đang đánh giá hội thoại. Quá trình này có thể mất vài phút, vui lòng chờ.' : 'Bạn có chắc chắn muốn kết thúc phiên và gửi tới Hệ thống Chấm điểm AI không?'}</p>
          </div>
        </div>
        <div className="practice-finish-info">
          <span className="practice-finish-info-icon" aria-hidden="true">i</span>
          <p>Hội thoại sẽ được đóng băng và đánh giá tự động dựa trên <strong>5 tiêu chí Rubric chuẩn</strong> cùng kiểm chứng thông số sản phẩm.</p>
        </div>
        <div className="practice-finish-actions">
          <button ref={cancelRef} type="button" className="practice-finish-cancel" onClick={onClose} disabled={finishing}>Tiếp tục luyện tập</button>
          <button type="button" className="practice-finish-confirm" onClick={onConfirm} disabled={finishing}>
            {finishing ? <><span className="practice-finish-spinner" aria-hidden="true" />Đang chấm điểm…</> : 'Hoàn tất & Chấm điểm'}
          </button>
        </div>
      </section>
    </div>
  );
}
