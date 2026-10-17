const REASONS = {
  input_blocked: 'Yêu cầu cần được diễn đạt lại để Copilot xử lý.',
  out_of_scope: 'Copilot hỗ trợ các tình huống tư vấn xe và tra cứu tài liệu.',
  insufficient_evidence: 'Một số nội dung chưa có đủ nguồn để xác minh.',
  policy_conflict: 'Các nguồn chưa thống nhất; cần đối chiếu trước khi tư vấn.',
  budget_exhausted: 'Đã đạt giới hạn xử lý. Hãy thu hẹp câu hỏi để tiếp tục.',
  verification_failed: 'Nội dung chưa được xác minh đầy đủ với nguồn.',
  retrieval_degraded: 'Một phần tra cứu đang tạm thời không khả dụng.',
};

export function copilotReason(reason) {
  return REASONS[reason] || '';
}
