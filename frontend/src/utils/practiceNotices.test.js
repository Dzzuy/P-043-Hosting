import test from 'node:test';
import assert from 'node:assert/strict';
import { apiErrorNotice, terminationNotice } from './practiceNotices.js';

const ids = (notice) => notice.actions.map((action) => action.id);
const cases = [
  ['provider_unavailable', 'Khách hàng chưa phản hồi', 'Tin nhắn của bạn đã được lưu, hãy thử lại.', ['retry_reply', 'close']],
  ['evaluation_failed', 'Chưa thể chấm điểm', 'Chưa thể chấm điểm lúc này. Vui lòng thử lại.', ['retry_finish', 'close']],
  ...['voice_not_configured', 'voice_failed'].map((code) => [code, 'Không dùng được giọng nói', 'Vui lòng nhập bằng bàn phím.', ['type_instead', 'close']]),
];
for (const [code, title, message, actionIds] of cases) {
  test(`${code}: exact copy and actions without technical details`, () => {
    const notice = apiErrorNotice({ code, status: 503, detail: 'Chi tiết nội bộ', message: 'Internal traceback' });
    assert.equal(notice.title, title);
    assert.equal(notice.message, message);
    assert.deepEqual(ids(notice), actionIds);
    assert.equal(notice.actions[0].kind, 'primary');
    assert.equal(notice.actions[1].kind, 'secondary');
    assert.equal('detail' in notice, false);
    assert.doesNotMatch(JSON.stringify(notice), /Chi tiết|traceback|503/);
  });
}
test('busy and oversized duration errors do not open a popup', () => {
  for (const code of ['session_busy', 'voice_too_long']) assert.equal(apiErrorNotice({ code }), null);
});
test('all other errors share the single generic notice', () => {
  for (const error of [
    ...['rate_limited', 'forbidden', 'session_not_found', 'validation_error', 'unknown'].map((code) => ({ code, detail: 'Chi tiết nội bộ' })),
    { status: 0 }, new TypeError('Failed to fetch'), {},
  ]) {
    const notice = apiErrorNotice(error);
    assert.equal(notice.title, 'Đã có lỗi xảy ra');
    assert.equal(notice.message, 'Vui lòng thử lại.');
    assert.deepEqual(ids(notice), ['close']);
  }
});
test('browser microphone failures use the voice unusable notice', () => {
  for (const name of ['NotAllowedError', 'NotFoundError']) {
    assert.deepEqual(apiErrorNotice({ name }), apiErrorNotice({ code: 'voice_failed' }));
  }
});
test('authentication has only a title and login action', () => {
  for (const error of [{ code: 'unauthenticated' }, { status: 401 }, { status: 401, code: 'session_busy' }]) {
    const notice = apiErrorNotice(error);
    assert.equal(notice.title, 'Phiên đăng nhập đã hết hạn');
    assert.equal(notice.message, undefined);
    assert.equal(notice.dismissible, false);
    assert.deepEqual(ids(notice), ['login']);
  }
});
test('ended notice preserves reason copy and always offers scoring and transcript', () => {
  const reasons = {
    max_turns: 'Đã hết số lượt trao đổi của phiên này.',
    advisor_ended: 'Bạn đã kết thúc cuộc trò chuyện.',
    dropped_out: 'Khách hàng đã rời cuộc trò chuyện vì băn khoăn chưa được giải đáp.',
    completed: 'Phiên luyện tập đã kết thúc.',
    other: 'Phiên luyện tập đã kết thúc.',
  };
  for (const [reason, message] of Object.entries(reasons)) {
    const notice = terminationNotice(reason, { scored: true });
    assert.equal(notice.message, message);
    assert.deepEqual(ids(notice), ['finish_and_score', 'review_transcript']);
    assert.deepEqual(apiErrorNotice({ code: 'session_finished' }, reason), terminationNotice(reason));
  }
  assert.equal(apiErrorNotice({ code: 'session_finished' }).message, reasons.other);
});
test('misconduct has no message and offers results only when already scored', () => {
  for (const scored of [true, false]) {
    const notice = terminationNotice('advisor_misconduct', { scored });
    assert.equal(notice.title, 'Phiên đã dừng do ngôn từ không phù hợp');
    assert.equal(notice.tone, 'warning');
    assert.equal('message' in notice, false);
    assert.deepEqual(ids(notice), [scored ? 'view_result' : 'finish_and_score', 'new_session']);
  }
});

test('message_not_sent preserves resend intent', () => {
  const notice = apiErrorNotice({ code: 'message_not_sent' });
  assert.equal(notice.title, 'Chưa gửi được tin nhắn');
  assert.equal(notice.message, 'Vui lòng gửi lại.');
  assert.deepEqual(ids(notice), ['resend', 'close']);
  assert.equal(notice.actions[0].kind, 'primary');
});
test('conflicts display curated Vietnamese detail', () => {
  for (const code of ['assignment_conflict', 'review_conflict']) {
    const notice = apiErrorNotice({ code, detail: 'Bài này đã được cập nhật.' });
    assert.equal(notice.message, 'Bài này đã được cập nhật.');
    assert.deepEqual(ids(notice), ['close']);
  }
});
test('playback and recording slips have no dialog', () => {
  for (const error of [
    { context: 'playback', name: 'NotAllowedError' },
    { context: 'playback', name: 'AbortError' },
    { context: 'playback', name: 'Error' },
    { context: 'recording', name: 'Error' },
    { code: 'voice_invalid_audio' }, { code: 'voice_empty_transcript' },
  ]) assert.equal(apiErrorNotice(error), null);
});
