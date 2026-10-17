import { Modal } from '../common/Modal';

const reviewLabel = (attempt) => {
  if (attempt.review_status === 'manager_approved') return 'Quản lý đã duyệt';
  if (attempt.evaluation_status === 'failed') return 'Chấm điểm thất bại';
  if (attempt.evaluation_status === 'pending') return 'Đã lưu • đang chấm điểm';
  return 'Bản nháp AI • chờ duyệt';
};

export function HistoryModal({ isOpen, onClose, attempts, status, error, onRetry, onSelectSession }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Lịch sử luyện tập" maxWidth={680}>
      {status === 'loading' && <p>Đang tải lịch sử...</p>}
      {status === 'error' && (
        <div role="alert">
          <p>Không tải được lịch sử: {error || 'Vui lòng thử lại.'}</p>
          <button className="btn-ghost" onClick={onRetry}>Thử lại</button>
        </div>
      )}
      {status === 'ready' && attempts.length === 0 && <p>Chưa có phiên luyện tập hoàn tất.</p>}
      {status === 'ready' && attempts.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {attempts.map((item) => (
            <button
              key={item.session_id}
              onClick={() => onSelectSession(item.session_id)}
              style={{ padding: 16, textAlign: 'left', border: '1px solid #E5E5E5', borderRadius: 10, background: '#FAFAFA', cursor: 'pointer' }}
            >
              <strong>{new Date(item.completed_at).toLocaleString('vi-VN')}</strong>
              <span style={{ display: 'block', fontSize: '0.82rem', color: '#555' }}>{reviewLabel(item)}</span>
              <span style={{ display: 'block', marginTop: 4 }}>
                {item.approved_score ?? item.ai_score ?? '—'} / 3
              </span>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
