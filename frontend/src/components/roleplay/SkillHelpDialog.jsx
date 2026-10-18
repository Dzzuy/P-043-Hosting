import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { CRITERIA } from '../../utils/scoreFormat';

const explanations = {
  need_discovery: 'Đặt câu hỏi khám phá để tìm hiểu đúng nhu cầu và điều khách hàng quan tâm hay vướng mắc.',
  product_knowledge: 'Giải thích đúng thông số, tính năng và lợi ích của xe; liên hệ với nhu cầu thực tế của khách hàng.',
  objection_handling: 'Ghi nhận băn khoăn, hỏi rõ nguyên nhân và đưa ra giải thích phù hợp, không gây áp lực cho khách hàng.',
  policy_accuracy: 'Tư vấn đúng giá, ưu đãi và các chính sách áp dụng; kiểm tra nguồn khi chưa chắc chắn, không tự hứa thêm quyền lợi.',
  closing_next_step: 'Đề xuất bước tiếp theo cụ thể như gửi thông tin, hẹn tư vấn hoặc lái thử và xác nhận sự đồng ý của khách hàng.',
};

export function SkillHelpDialog({ onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    element.showModal();
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      previousFocus?.focus();
    };
  }, []);
  return createPortal(
    <dialog ref={dialog} className="ap-skill-help" aria-labelledby="ap-skill-help-title" onCancel={onClose} onClick={(event) => {
      if (event.target !== event.currentTarget) return;
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    }}>
      <header><h2 id="ap-skill-help-title">5 kỹ năng tư vấn</h2><button type="button" onClick={onClose} aria-label="Đóng giải thích kỹ năng"><X size={20} aria-hidden="true" /></button></header>
      <p>Biểu đồ thể hiện điểm của bạn theo từng kỹ năng:</p>
      <dl>{CRITERIA.map(({ key, label }) => <div key={key}><dt>{label}</dt><dd>{explanations[key]}</dd></div>)}</dl>
      <button type="button" className="ap-skill-help-done" onClick={onClose}>Đã hiểu</button>
    </dialog>, document.body,
  );
}
