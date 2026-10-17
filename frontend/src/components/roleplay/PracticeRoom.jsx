import { useState, useRef, useEffect } from 'react';
import { ChevronLeft, SendIcon, FlagIcon, TargetIcon, MicIcon, UsersIcon, PhoneIcon, SpeakerIcon } from '../common/Icons';
import { Badge } from '../common/Badge';
import { getVehicleImage } from '../../data/vehicleData';
import { Button } from '../common/Button';
import { Modal } from '../common/Modal';
import { practiceApi } from '../../api/practiceApi';
import { createId } from '../../lib/id';
import { usePushToTalk } from '../../hooks/usePushToTalk';
import './PracticeRoomVoice.css';
import { NoticeDialog } from '../common/NoticeDialog';
import { apiErrorNotice, terminationNotice } from '../../utils/practiceNotices';
import { authApi } from '../../api/authApi';

const VOICE_SEND_PREFERENCE_KEY = 'practice.voice.autoSend';

export function PracticeRoom({
  scenario,
  session,
  onFinish,
  onSavedAttempt,
  onExit,
}) {
  const [messages, setMessages] = useState(session?.messages || []);

  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [turnCount, setTurnCount] = useState(session?.turn_count || 0);
  const [stage, setStage] = useState(session?.conversation_stage || 'opening');
  const [terminationStatus, setTerminationStatus] = useState(session?.termination_status || 'active');
  const [pendingReply, setPendingReply] = useState(session?.pending_customer_reply || false);
  const [showFinishConfirm, setShowFinishConfirm] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [notice, setNotice] = useState(null);
  const endedNoticeRef = useRef(null);
  const inputRef = useRef(null);
  const [voiceHint, setVoiceHint] = useState('');
  const resendTextRef = useRef('');
  const showError = async (error) => {
    console.debug('Practice request failed', { status: error.status, code: error.code, name: error.name });
    let reason = terminationStatus;
    if (error.code === 'session_finished') {
      endedNoticeRef.current = 'rejected';
      try {
        const saved = await practiceApi.getSession(session.session_id);
        reason = saved.termination_status;
        setMessages(saved.messages);
        setPendingReply(saved.pending_customer_reply);
      } catch (refreshError) {
        console.debug('Practice session refresh failed', { code: refreshError.code });
        reason = 'completed';
      }
      setTerminationStatus(reason);
    }
    const nextNotice = apiErrorNotice(error, reason);
    if (nextNotice) setNotice(nextNotice);
    else if (['voice_invalid_audio', 'voice_empty_transcript', 'voice_too_long'].includes(error.code)) {
      setVoiceHint('Không nghe rõ, hãy giữ nút lâu hơn và nói lại.');
    }
  };
  useEffect(() => {
    if (terminationStatus === 'active' || endedNoticeRef.current) return;
    endedNoticeRef.current = terminationStatus;
    if (!session?.result) queueMicrotask(() => setNotice((current) => current || terminationNotice(terminationStatus)));
  }, [terminationStatus, session?.result]);
  const [mode, setMode] = useState('text');
  const [autoSendPreference, setAutoSendPreference] = useState(() => {
    try {
      const saved = localStorage.getItem(VOICE_SEND_PREFERENCE_KEY);
      return saved !== 'false';
    } catch {
      return true;
    }
  });
  const chooseAutoSend = (value) => {
    setAutoSendPreference(value);
    try {
      localStorage.setItem(VOICE_SEND_PREFERENCE_KEY, String(value));
    } catch {
      // Storage may be unavailable; retain the preference for this room.
    }
  };
  const voiceGender = scenario?.voice_gender;
  const [transcribing, setTranscribing] = useState(false);
  const [speakingId, setSpeakingId] = useState(null);

  const chatEndRef = useRef(null);
  const audioRef = useRef(null);
  const audioUrlsRef = useRef(new Map());
  const modeRef = useRef(mode);
  const sendingRef = useRef(false);
  const sendHandlerRef = useRef(null);

  useEffect(() => { modeRef.current = mode; }, [mode]);

  const onRecorded = async (blob, durationSeconds) => {
    if (blob.size > 4_000_000) {
      showError({ code: 'voice_invalid_audio' });
      return;
    }
    setVoiceHint('');
    setTranscribing(true);
    try {
      const result = await practiceApi.transcribeVoice(session.session_id, blob, durationSeconds);
      if (!result.transcript.trim()) {
        showError({ code: 'voice_invalid_audio' });
        return;
      }
      setInputMessage(result.transcript);
      if (autoSendPreference) {
        setTranscribing(false);
        await sendHandlerRef.current?.(result.transcript, true);
      }
    } catch (requestError) {
      showError(requestError);
    } finally {
      setTranscribing(false);
    }
  };

  const recorder = usePushToTalk(onRecorded);

  const playCustomer = async (message, automatic = false) => {
    if (!message || message.role !== 'customer') return;
    if (automatic && modeRef.current !== 'voice') return;
    if (!voiceGender) {
      showError({ code: 'voice_not_configured' });
      return;
    }
    const cacheKey = `${message.message_id}:${voiceGender}`;
    setSpeakingId(message.message_id);
    try {
      let url = audioUrlsRef.current.get(cacheKey);
      if (!url) {
        const blob = await practiceApi.customerSpeech(session.session_id, message.message_id, voiceGender);
        url = URL.createObjectURL(blob);
        audioUrlsRef.current.set(cacheKey, url);
      }
      if (automatic && modeRef.current !== 'voice') {
        setSpeakingId(null);
        return;
      }
      audioRef.current?.pause();
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setSpeakingId(null);
      try {
        await audio.play();
      } catch (playbackError) {
        console.debug('Practice audio playback interrupted', { name: playbackError.name });
        setVoiceHint('Nhấn nút loa để nghe lại.');
        setSpeakingId(null);
      }
    } catch (requestError) {
      showError(requestError);
      setSpeakingId(null);
    }
  };

  const stageLabels = {
    opening: 'Giai đoạn: Chào hỏi & Mở đầu',
    discovery: 'Giai đoạn: Khai thác nhu cầu',
    presentation: 'Giai đoạn: Giới thiệu giải pháp',
    objection_handling: 'Giai đoạn: Xử lý băn khoăn',
    closing: 'Giai đoạn: Chốt & Hướng dẫn',
    completed: 'Giai đoạn: Hoàn thành',
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, mode]);

  useEffect(() => () => {
    audioRef.current?.pause();
    audioUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const toggleVoiceMode = () => {
    if (recorder.recordingState !== 'idle' || transcribing) return;
    const nextMode = modeRef.current === 'voice' ? 'text' : 'voice';
    modeRef.current = nextMode;
    setMode(nextMode);
    // Starting a call always begins with auto-send on; the user can still switch it off.
    if (nextMode === 'voice') chooseAutoSend(true);
    if (nextMode === 'text') {
      audioRef.current?.pause();
      setSpeakingId(null);
    }
  };

  async function handleSendMessage(message = inputMessage, fromVoice = false) {
    const text = typeof message === 'string' ? message.trim() : inputMessage.trim();
    if (!text || sendingRef.current || loading || finishing || pendingReply || (!fromVoice && transcribing) || (!fromVoice && recorder.recordingState !== 'idle') || terminationStatus !== 'active') return;
    sendingRef.current = true;

    const advisorMsg = {
      message_id: createId('adv'),
      role: 'advisor',
      content: text,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, advisorMsg]);
    setLoading(true);
    setNotice(null);

    try {
      const updated = await practiceApi.sendMessage(session.session_id, text);
      setMessages(updated.messages);
      setStage(updated.conversation_stage);
      setTurnCount(updated.turn_count);
      setTerminationStatus(updated.termination_status);
      setPendingReply(updated.pending_customer_reply);
      setInputMessage('');
      if (modeRef.current === 'voice') {
        const customerReply = updated.messages.at(-1);
        if (customerReply?.role === 'customer') playCustomer(customerReply, true);
      }
    } catch (requestError) {
      if (requestError.code === 'message_not_sent') {
        resendTextRef.current = text;
        setInputMessage(text);
        setMessages((previous) => previous.filter((item) => item.message_id !== advisorMsg.message_id));
      }
      await showError(requestError);
      try {
        const saved = await practiceApi.getSession(session.session_id);
        setMessages(saved.messages);
        setStage(saved.conversation_stage);
        setTurnCount(saved.turn_count);
        setTerminationStatus(saved.termination_status);
        setPendingReply(saved.pending_customer_reply);
        if (requestError.code === 'provider_unavailable') setInputMessage('');
      } catch {
        // Keep the advisor's visible draft; do not fabricate a customer reply.
      }
    } finally {
      sendingRef.current = false;
      setLoading(false);
    }
  }

  useEffect(() => { sendHandlerRef.current = handleSendMessage; });

  async function handleRetryReply() {
    if (loading || finishing || transcribing || recorder.recordingState !== 'idle') return;
    setLoading(true);
    setNotice(null);
    try {
      const updated = await practiceApi.retryCustomerReply(session.session_id);
      setMessages(updated.messages);
      setStage(updated.conversation_stage);
      setTurnCount(updated.turn_count);
      setTerminationStatus(updated.termination_status);
      setPendingReply(updated.pending_customer_reply);
      if (modeRef.current === 'voice') {
        const customerReply = updated.messages.at(-1);
        if (customerReply?.role === 'customer') playCustomer(customerReply, true);
      }
    } catch (requestError) {
      showError(requestError);
      try {
        const saved = await practiceApi.getSession(session.session_id);
        setMessages(saved.messages);
        setStage(saved.conversation_stage);
        setTurnCount(saved.turn_count);
        setTerminationStatus(saved.termination_status);
        setPendingReply(saved.pending_customer_reply);
      } catch {
        // Keep the saved pending turn visible until the session can be loaded.
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFinishSession = async () => {
    if (loading || finishing || pendingReply || transcribing || recorder.recordingState !== 'idle') return;
    setFinishing(true);
    setNotice(null);
    try {
      const resultView = await practiceApi.finishSession(session.session_id);
      onFinish(resultView);
    } catch (requestError) {
      try {
        const saved = await practiceApi.getSession(session.session_id);
        setTerminationStatus(saved.termination_status);
        setPendingReply(saved.pending_customer_reply);
        setMessages(saved.messages);
        if (saved.termination_status !== 'active') {
          const detail = await practiceApi.getAttempt(session.session_id);
          if (detail.ai_evaluation?.result) {
            await onSavedAttempt(session.session_id);
            return;
          }
        }
      } catch (refreshError) {
        console.debug('Practice finish reconciliation failed', { code: refreshError.code });
      }
      await showError(requestError.code || requestError.status === 401
        ? requestError : { code: 'evaluation_failed' });
    } finally {
      setFinishing(false);
      setShowFinishConfirm(false);
    }
  };

  useEffect(() => {
    if (!recorder.permissionError) return;
    console.debug('Practice microphone permission unavailable', { name: recorder.permissionError.name });
    queueMicrotask(() => setNotice(apiErrorNotice(recorder.permissionError)));
  }, [recorder.permissionError]);

  const handleNoticeAction = async (id) => {
    setNotice(null);
    if (id === 'finish_and_score' || id === 'retry_finish') await handleFinishSession();
    else if (id === 'view_result') await onSavedAttempt(session.session_id);
    else if (id === 'new_session') onExit();
    else if (id === 'resend') await handleSendMessage(resendTextRef.current);
    else if (id === 'retry_reply') await handleRetryReply();
    else if (id === 'login') {
      try { await authApi.logout(); } finally { window.location.reload(); }
    } else if (id === 'type_instead') {
      setMode('text');
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  return (
    <div className="practice-room-container">
      <NoticeDialog notice={notice} onAction={handleNoticeAction} onClose={() => setNotice(null)} />
      {/* ROOM HEADER */}
      <div className="practice-room-header">
        <div className="practice-room-header-main">
          <button
            onClick={onExit}
            className="practice-room-back"
          >
            <ChevronLeft style={{ width: 16, height: 16 }} />
            <span>Rời phòng</span>
          </button>

          {getVehicleImage(scenario?.model_badge || scenario?.model || scenario?.title) && (
            <div className="practice-room-vehicle">
              <img
                src={getVehicleImage(scenario?.model_badge || scenario?.model || scenario?.title)}
                alt={scenario?.model_badge || scenario?.model}
              />
            </div>
          )}

          <div className="practice-room-identity">
            <h2>{scenario?.title}</h2>
            <div className="practice-room-meta">
              <Badge variant="highlight">{scenario?.model_badge || scenario?.model}</Badge>
              <span>{stageLabels[stage] || stage}</span>
              <span>Lượt trao đổi: {turnCount}</span>
            </div>
          </div>
        </div>

        <button
          className="practice-room-finish"
          onClick={() => setShowFinishConfirm(true)}
          disabled={loading || finishing || pendingReply || transcribing || recorder.recordingState !== 'idle'}
        >
          <FlagIcon style={{ width: 14, height: 14 }} /> Kết thúc & Chấm điểm
        </button>
      </div>

      {/* CUSTOMER CONTEXT BANNER */}
      <div className="practice-room-context">
        <div className="practice-room-context-item">
          <UsersIcon aria-hidden="true" />
          <div><strong>Khách hàng · {scenario?.sales_channel || 'Kênh tư vấn'}</strong><p>{session?.visible_context}</p></div>
        </div>
        <div className="practice-room-context-item">
          <TargetIcon aria-hidden="true" />
          <div><strong>Mục tiêu luyện tập</strong><p>{scenario?.training_objective}</p></div>
        </div>
      </div>

      {/* CHAT THREAD */}
      <div className="practice-room-messages">
        {messages.length === 0 && (
          <p role="status">Bạn là tư vấn viên — hãy mở lời chào khách trước.</p>
        )}
        {messages.map((m, idx) => (
          <div
            key={m.message_id || idx}
            className={`practice-room-message ${m.role === 'advisor' ? 'practice-room-message-advisor' : 'practice-room-message-customer'}`}
          >
            <div className="practice-room-bubble">
              <div className="practice-room-speaker">
                {m.role === 'advisor' ? 'Bạn (Tư vấn viên)' : 'Khách hàng'}
              </div>
              <div className="practice-room-message-content">{m.content}</div>
              {m.role === 'customer' && (
                <button
                  type="button"
                  className="practice-room-play-voice"
                  onClick={() => playCustomer(m)}
                  disabled={speakingId === m.message_id}
                  aria-label={speakingId === m.message_id ? 'Đang phát giọng khách' : 'Phát giọng khách'}
                >
                  <SpeakerIcon aria-hidden="true" />
                  <span className="sr-only">{speakingId === m.message_id ? 'Đang phát giọng khách' : 'Phát giọng khách'}</span>
                </button>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="practice-room-message practice-room-message-customer">
            <div className="practice-room-bubble practice-room-loading" role="status">
              Khách hàng đang soạn câu trả lời...
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {terminationStatus === 'active' && (
        <div className="practice-room-voice-stage">
          <div className="practice-room-voice-stage-title">{mode === 'voice' ? 'Trò chuyện bằng giọng nói' : 'Hội thoại bằng giọng nói'}</div>
          <div className="practice-room-voice-controls">
            <button
              type="button"
              className={`practice-room-voice-bubble ${recorder.recordingState === 'recording' ? 'recording' : ''}`}
              onPointerDown={(event) => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); recorder.start(); }}
              onPointerUp={recorder.stop}
              onPointerCancel={recorder.stop}
              onLostPointerCapture={recorder.stop}
              onBlur={recorder.stop}
              onKeyDown={(event) => { if (!event.repeat && [' ', 'Enter'].includes(event.key)) { event.preventDefault(); recorder.start(); } }}
              onKeyUp={(event) => { if ([' ', 'Enter'].includes(event.key)) { event.preventDefault(); recorder.stop(); } }}
              disabled={loading || finishing || pendingReply || transcribing || speakingId !== null}
              aria-label={autoSendPreference ? 'Bấm giữ để nói, thả để gửi' : 'Bấm giữ để nói, thả để chép vào ô nhập'}
            >
              <span className="practice-room-voice-glow" aria-hidden="true" />
              <MicIcon aria-hidden="true" />
            </button>
            <div className="practice-room-auto-send-group">
              <button
                type="button"
                role="switch"
                className="practice-room-auto-send"
                aria-checked={autoSendPreference}
                aria-label="Tự động gửi"
                aria-describedby="practice-room-auto-send-hint"
                onClick={() => chooseAutoSend(!autoSendPreference)}
                disabled={loading || finishing || pendingReply || transcribing || recorder.recordingState !== 'idle'}
              >
                <span className="practice-room-auto-send-track" aria-hidden="true">
                  <span className="practice-room-auto-send-knob" />
                </span>
                <span>Tự động gửi</span>
              </button>
              <span id="practice-room-auto-send-hint" className="practice-room-auto-send-hint">
                {autoSendPreference ? 'Giữ tối đa 90 giây rồi thả để gửi tự động' : 'Giữ tối đa 90 giây, thả rồi sửa bản chép và nhấn Gửi'}
              </span>
            </div>
          </div>
          <span className="practice-room-voice-label">Bấm giữ để nói</span>
          <span className="practice-room-voice-status" role="status">
            {recorder.recordingState === 'requesting' ? 'Đang xin quyền micro...'
              : recorder.recordingState === 'recording' ? (autoSendPreference ? 'Đang ghi âm · Thả để gửi' : 'Đang ghi âm · Thả để chép vào ô nhập')
                : transcribing ? 'Đang chuyển giọng nói thành chữ...'
                  : loading ? 'Khách hàng đang trả lời...'
                    : speakingId ? 'Đang phát giọng khách...'
                      : ''}
          </span>

        </div>
      )}

      {(voiceHint || recorder.recordingError) && <p className="practice-room-composer-hint" role="status">{voiceHint || recorder.recordingError}</p>}
      {/* INPUT BAR */}
      <div className="practice-room-composer">
        {pendingReply && (
          <div className="practice-room-retry">
            <span style={{ fontSize: '0.82rem' }}>Tin nhắn đã lưu. Khách hàng chưa phản hồi.</span>
            <button className="btn-primary" onClick={handleRetryReply} disabled={loading || finishing || transcribing || recorder.recordingState !== 'idle'}>Thử lại phản hồi</button>
          </div>
        )}
        {terminationStatus !== 'active' && <p role="status" style={{ fontSize: '0.82rem', marginBottom: 8, color: terminationStatus === 'advisor_misconduct' ? '#991B1B' : undefined }}>{terminationStatus === 'advisor_misconduct'
          ? 'Phiên luyện tập đã dừng do ngôn từ không phù hợp.'
          : 'Cuộc trò chuyện đã kết thúc. Hãy xem đánh giá.'}</p>}
        <div className="practice-room-composer-form">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            placeholder="Nhắn tin cho khách hàng..."
            aria-label="Nhắn tin cho khách hàng"
            rows={1}
            disabled={loading || finishing || pendingReply || transcribing || recorder.recordingState !== 'idle' || terminationStatus !== 'active'}
          />
          <button
            type="button"
            onClick={() => handleSendMessage()}
            disabled={!inputMessage.trim() || loading || finishing || pendingReply || transcribing || recorder.recordingState !== 'idle' || terminationStatus !== 'active'}
            className="practice-room-send"
            title="Gửi tin nhắn"
          >
            <SendIcon style={{ width: 16, height: 16 }} />
            <span className="sr-only">Gửi</span>
          </button>
          <button
            type="button"
            onClick={toggleVoiceMode}
            disabled={recorder.recordingState !== 'idle' || transcribing || terminationStatus !== 'active'}
            className={`practice-room-control practice-room-mode-toggle ${mode === 'voice' ? 'active' : ''}`}
            aria-label={mode === 'voice' ? 'Tắt chế độ hội thoại' : 'Bật chế độ hội thoại'}
            aria-pressed={mode === 'voice'}
            title={mode === 'voice' ? 'Tắt chế độ hội thoại' : 'Bật chế độ hội thoại'}
          >
            <PhoneIcon aria-hidden="true" />
          </button>
        </div>
        {!autoSendPreference && transcribing && <p className="practice-room-composer-hint" role="status">Đang chuyển giọng nói thành chữ. Kiểm tra bản chép rồi nhấn Gửi.</p>}
      </div>

      {/* FINISH MODAL */}
      <Modal
        isOpen={showFinishConfirm}
        onClose={() => setShowFinishConfirm(false)}
        title="Xác nhận hoàn tất phiên thực chiến"
        maxWidth={500}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={{ fontSize: '0.92rem', color: '#333333', lineHeight: 1.5 }}>
            Bạn có chắc chắn muốn kết thúc phiên và gửi tới Hệ thống Chấm điểm AI không?
          </p>
          <div style={{ backgroundColor: '#F7F7F5', padding: '12px 16px', borderRadius: 8, fontSize: '0.82rem', color: '#555555' }}>
            Hội thoại sẽ được đóng băng và đánh giá tự động dựa trên <strong>5 tiêu chí Rubric chuẩn</strong> cùng kiểm chứng thông số sản phẩm.
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <Button variant="outline" onClick={() => setShowFinishConfirm(false)}>
              Tiếp tục luyện tập
            </Button>
            <Button variant="primary" loading={finishing} onClick={handleFinishSession}>
              Hoàn tất & Chấm điểm
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
