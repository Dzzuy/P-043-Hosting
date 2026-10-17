export const GENERIC_PRACTICE_ERROR = 'Vui lòng thử lại.';
const labels = {
  finish_and_score: 'Kết thúc & Chấm điểm', review_transcript: 'Xem hội thoại',
  view_result: 'Xem kết quả', new_session: 'Luyện tập phiên mới',
  retry_reply: 'Thử lại phản hồi', retry_finish: 'Thử chấm điểm lại',
  resend: 'Gửi lại', type_instead: 'Nhập bằng bàn phím', login: 'Đăng nhập lại', close: 'Đóng',
};
const actions = (ids) => ids.map((id, index) => ({ id, label: labels[id], kind: index ? 'secondary' : 'primary' }));

export function terminationNotice(status, { scored = false } = {}) {
  const reason = status && typeof status === 'object' ? status.reason || status.termination_status || status.status : status;
  if (reason === 'advisor_misconduct') {
    return { tone: 'warning', title: 'Phiên đã dừng do ngôn từ không phù hợp', actions: actions([scored ? 'view_result' : 'finish_and_score', 'new_session']), dismissible: true };
  }
  const messages = {
    max_turns: 'Đã hết số lượt trao đổi của phiên này.',
    advisor_ended: 'Bạn đã kết thúc cuộc trò chuyện.',
    dropped_out: 'Khách hàng đã rời cuộc trò chuyện vì băn khoăn chưa được giải đáp.',
  };
  return { tone: 'info', title: 'Phiên luyện tập đã kết thúc', message: messages[reason] || 'Phiên luyện tập đã kết thúc.', actions: actions(['finish_and_score', 'review_transcript']), dismissible: true };
}

// Null means the UI already prevents this case; callers only log it for developers.
export function apiErrorNotice(error = {}, termination = null) {
  const code = error.status === 401 ? 'unauthenticated' : error.code;
  if (error.context === 'playback' || (error.context === 'recording' && !['NotAllowedError', 'NotFoundError'].includes(error.name)) || ['voice_invalid_audio', 'voice_empty_transcript'].includes(code)) return null;
  if (code === 'message_not_sent') return { tone: 'error', title: 'Chưa gửi được tin nhắn', message: 'Vui lòng gửi lại.', actions: actions(['resend', 'close']), dismissible: true };
  if (['assignment_conflict', 'review_conflict'].includes(code)) return { tone: 'warning', title: 'Không thể cập nhật', message: error.detail || GENERIC_PRACTICE_ERROR, actions: actions(['close']), dismissible: true };
  if (code === 'session_busy' || code === 'voice_too_long') return null;
  if (code === 'session_finished') return terminationNotice(termination);
  if (code === 'unauthenticated') return { tone: 'warning', title: 'Phiên đăng nhập đã hết hạn', actions: actions(['login']), dismissible: false };
  if (['voice_not_configured', 'voice_failed'].includes(code) || ['NotAllowedError', 'NotFoundError'].includes(error.name)) {
    return { tone: 'warning', title: 'Không dùng được giọng nói', message: 'Vui lòng nhập bằng bàn phím.', actions: actions(['type_instead', 'close']), dismissible: true };
  }
  if (code === 'provider_unavailable') return { tone: 'error', title: 'Khách hàng chưa phản hồi', message: 'Tin nhắn của bạn đã được lưu, hãy thử lại.', actions: actions(['retry_reply', 'close']), dismissible: true };
  if (code === 'evaluation_failed') return { tone: 'error', title: 'Chưa thể chấm điểm', message: 'Chưa thể chấm điểm lúc này. Vui lòng thử lại.', actions: actions(['retry_finish', 'close']), dismissible: true };
  return { tone: 'error', title: 'Đã có lỗi xảy ra', message: GENERIC_PRACTICE_ERROR, actions: actions(['close']), dismissible: true };
}
