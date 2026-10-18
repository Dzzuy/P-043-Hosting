import test from 'node:test';
import process from 'node:process';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse } from '@babel/parser';
import { apiErrorNotice } from '../../utils/practiceNotices.js';

const source = process.env.REGRESSION_BASELINE
  ? readFileSync(process.env.REGRESSION_BASELINE, 'utf8')
  : readFileSync(new URL('./PracticeRoom.jsx', import.meta.url), 'utf8');
function handler(name, scope, text = source) {
  const ast = parse(text, { sourceType: 'module', plugins: ['jsx'] });
  let found;
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'FunctionDeclaration' && node.id.name === name) found = node;
    if (node.type === 'VariableDeclarator' && node.id.name === name) found = node.init.type === 'CallExpression' ? node.init.arguments[0] : node.init;
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value === 'object') walk(value);
    }
  }
  walk(ast);
  return new Function(...Object.keys(scope), `return (${text.slice(found.start, found.end)})`)(...Object.values(scope));
}
function room() {
  const state = { draft: 'Xin chào', messages: [], termination: 'active', notice: null, opened: false };
  const scope = {
    inputMessage: state.draft, sendingRef: { current: false }, loading: false, finishing: false,
    pendingReply: false, transcribing: false, recorder: { recordingState: 'idle' }, terminationStatus: 'active',
    session: { session_id: 's' }, messages: [], createId: () => 'adv',
    resendTextRef: { current: '' }, modeRef: { current: 'text' },
    setMessages: (value) => { state.messages = typeof value === 'function' ? value(state.messages) : value; },
    setInputMessage: (value) => { state.draft = value; },
    setTerminationStatus: (value) => { state.termination = value; },
    setNotice: (value) => { state.notice = value; },
    setStage() {}, setTurnCount() {}, setPendingReply() {}, setLoading() {}, setFinishing() {}, setShowFinishConfirm() {},
    onFinish() {}, onSavedAttempt: async () => { state.opened = true; },
    showError: async (error) => { state.notice = apiErrorNotice(error); },
    practiceApi: {},
  };
  return { state, scope };
}
test('send retains draft until success and restores unsaved text for resend', async () => {
  const { state, scope } = room();
  scope.practiceApi.sendMessage = async () => {
    assert.equal(state.draft, 'Xin chào');
    throw { code: 'message_not_sent' };
  };
  scope.practiceApi.getSession = async () => { throw new Error('offline'); };
  await handler('handleSendMessage', scope)();
  assert.equal(state.draft, 'Xin chào');
  assert.equal(scope.resendTextRef.current, 'Xin chào');
  assert.deepEqual(state.messages, []);
});
for (const code of ['evaluation_failed', undefined]) {
  test(`finish ${code || 'lost response'} disables ended room and reopens saved result`, async () => {
    const { state, scope } = room();
    scope.practiceApi.finishSession = async () => { throw { code }; };
    scope.practiceApi.getSession = async () => ({ termination_status: 'advisor_ended', messages: [] });
    scope.practiceApi.getAttempt = async () => ({ ai_evaluation: { result: { score: 3 } } });
    await handler('handleFinishSession', scope)();
    assert.equal(state.termination, 'advisor_ended');
    assert.equal(state.opened, true);
  });
}
test('finish with missing evaluation disables ended room and keeps retry', async () => {
  const { state, scope } = room();
  scope.practiceApi.finishSession = async () => { throw { code: 'evaluation_failed' }; };
  scope.practiceApi.getSession = async () => ({ termination_status: 'advisor_ended', messages: [] });
  scope.practiceApi.getAttempt = async () => ({ ai_evaluation: { result: null } });
  await handler('handleFinishSession', scope)();
  assert.equal(state.termination, 'advisor_ended');
  assert.equal(state.notice.actions[0].id, 'retry_finish');
});
test('session_finished uses refreshed server reason', async () => {
  const { state, scope } = room();
  scope.endedNoticeRef = { current: null };
  scope.apiErrorNotice = apiErrorNotice;
  scope.setVoiceHint = () => {};
  scope.practiceApi.getSession = async () => ({ termination_status: 'dropped_out', messages: [] });
  await handler('showError', scope)({ code: 'session_finished' });
  assert.equal(state.termination, 'dropped_out');
  assert.match(state.notice.message, /rời cuộc trò chuyện/);
});
for (const name of ['NotAllowedError', 'AbortError', 'Error']) {
  test(`playback ${name} only shows inline replay hint`, async () => {
    const { state, scope } = room();
    let hint = '';
    Object.assign(scope, {
      voiceGender: 'female', audioUrlsRef: { current: new Map([['customer:female', 'blob:cached']]) },
      audioRef: { current: null }, setSpeakingId() {},
      setVoiceHint: (value) => { hint = value; },
      Audio: class { async play() { throw { name }; } },
    });
    await handler('playCustomer', scope)({ message_id: 'customer', role: 'customer' });
    assert.equal(hint, 'Nhấn nút loa để nghe lại.');
    assert.equal(state.notice, null);
    assert.equal(scope.modeRef.current, 'text');
  });
}
test('empty transcript keeps draft and reports inline slip without dialog', async () => {
  const { state, scope } = room();
  let hint = '';
  Object.assign(scope, {
    setTranscribing() {}, setVoiceHint: (value) => { hint = value; }, autoSendPreference: true,
    showError: async (error) => {
      state.notice = apiErrorNotice(error);
      if (!state.notice) hint = 'Không nghe rõ';
    },
  });
  scope.practiceApi.transcribeVoice = async () => ({ transcript: '  ' });
  await handler('onRecorded', scope)({ size: 200 }, 1);
  assert.equal(state.draft, 'Xin chào');
  assert.equal(state.notice, null);
  assert.ok(hint);
});

const viewSource = process.env.REGRESSION_VIEW_BASELINE
  ? readFileSync(process.env.REGRESSION_VIEW_BASELINE, 'utf8')
  : readFileSync(new URL('./RoleplayView.jsx', import.meta.url), 'utf8');
for (const name of ['loadHistory', 'handleStartScenario', 'openAttempt']) {
  for (const error of [{ status: 401 }, { code: 'session_busy' }]) {
    test(`${name} ${error.code || '401'} renders fallback and routes notice`, async () => {
      let message;
      let notice;
      const reject = async () => { throw error; };
      const scope = {
        apiErrorNotice, scenarios: [{ scenario_id: 's' }], starting: false,
        practiceApi: { getHistory: reject, startSession: reject, getAttempt: reject },
        setNotice: (value) => { notice = value; },
        setHistoryError: (value) => { message = value; },
        setStartError: (value) => { message = value; },
        setHistory() {}, setHistoryStatus() {}, setActiveScenario() {}, setStarting() {}, setLastMaxTurns() {}, setInitialMode() {},
        setActiveSession() {}, setViewMode() {}, setHistoryScenarioId() {}, setSelectedSessionId() {},
        setDetailStatus() {}, setAttemptDetail() {}, setRetryEvaluationError() {},
      };
      await handler(name, scope, viewSource)('s');
      assert.ok(message);
      if (error.status === 401) assert.equal(notice.actions[0].id, 'login');
    });
  }
}

test('dead evaluation state, autosend alias and duplicate style are removed', () => {
  assert.doesNotMatch(viewSource, /retryEvaluationError|setRetryEvaluationError/);
  assert.doesNotMatch(source, /const autoSend =/);
  const css = readFileSync(new URL('./PracticeRoomVoice.css', import.meta.url), 'utf8');
  assert.equal((css.match(/\.practice-room-auto-send \{/g) || []).length, 1);
});

const hookSource = readFileSync(new URL('../../hooks/usePushToTalk.js', import.meta.url), 'utf8');
for (const name of ['NotAllowedError', 'NotFoundError', 'NotReadableError']) {
  test(`getUserMedia ${name} exposes permission errors only for denied or missing microphone`, async () => {
    let permission = null;
    let hint = '';
    const scope = {
      recorderRef: { current: null }, recordingState: 'idle', pendingStopRef: { current: false },
      failedRef: { current: false }, window: { MediaRecorder: class {} },
      navigator: { mediaDevices: { getUserMedia: async () => { throw { name }; } } },
      setRecordingError: (value) => { hint = value; }, setRecordingState() {},
      setPermissionError: (value) => { permission = value; }, release() {},
    };
    await handler('start', scope, hookSource)();
    assert.ok(hint);
    assert.equal(permission?.name || null, name === 'NotReadableError' ? null : name);
  });
}

test('retry evaluation keeps progress dialog visible until request settles', async () => {
  const { state, scope } = room();
  let dialogOpen = false;
  let finishing = false;
  let rejectRequest;
  scope.setShowFinishConfirm = (value) => { dialogOpen = value; };
  scope.setFinishing = (value) => { finishing = value; };
  state.notice = apiErrorNotice({ code: 'evaluation_failed' });
  scope.practiceApi.finishSession = () => new Promise((_, reject) => { rejectRequest = reject; });
  scope.practiceApi.getSession = async () => ({ termination_status: 'advisor_ended', messages: [] });
  scope.practiceApi.getAttempt = async () => ({ ai_evaluation: null });
  scope.handleFinishSession = handler('handleFinishSession', scope);
  const pending = handler('handleNoticeAction', scope)('retry_finish');
  assert.equal(state.notice, null);
  assert.equal(dialogOpen, true);
  assert.equal(finishing, true);
  rejectRequest({ code: 'evaluation_failed' });
  await pending;
  assert.equal(dialogOpen, false);
  assert.equal(finishing, false);
  assert.equal(state.notice.actions[0].id, 'retry_finish');
});
