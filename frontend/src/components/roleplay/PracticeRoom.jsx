import { useState, useRef, useEffect } from 'react';
import { ChevronLeft, SendIcon, MicIcon, SpeakerIcon } from '../common/Icons';
import { Video, VideoOff, ShieldCheck, Clock, X, Captions, CaptionsOff, MessageCircle, Phone } from 'lucide-react';
import { getVehicleImage } from '../../data/vehicleData';
import { FinishConfirmDialog } from './FinishConfirmDialog';
import { practiceApi } from '../../api/practiceApi';
import { createId } from '../../lib/id';
import { usePushToTalk } from '../../hooks/usePushToTalk';
import { useLocalCamera } from '../../hooks/useLocalCamera';
import './practiceRoom.css';
import { NoticeDialog } from '../common/NoticeDialog';
import { apiErrorNotice, terminationNotice } from '../../utils/practiceNotices';
import { authApi } from '../../api/authApi';

const VOICE_SEND_PREFERENCE_KEY = 'practice.voice.autoSend';

function readPreference(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function savePreference(key, value) {
  try { localStorage.setItem(key, value); } catch { /* Room works without storage. */ }
}
function clock(seconds) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
function makeBands(green) {
  const radii = green ? [62, 84, 108, 134, 162] : [98, 127, 158, 191, 226, 263, 302, 340];
  return radii.map((radius, i) => {
    const inner = i ? radii[i - 1] : green ? 48 : 76;
    const step = green ? 16 : 22;
    const size = green ? 4.5 - .5 * i : 5 - .4 * i;
    const alpha = .85 * (1 - i / radii.length) ** (green ? 1.2 : 1.3);
    const dots = [];
    for (let x = -Math.ceil(radius / step); x <= Math.ceil(radius / step); x++) {
      for (let y = -Math.ceil(radius / step); y <= Math.ceil(radius / step); y++) {
        const distance = Math.hypot(x * step, y * step);
        if (distance >= inner && distance < radius) dots.push({ left: radius + x * step - size / 2, top: radius + y * step - size / 2 });
      }
    }
    return { radius, size, color: `rgba(${green ? '21,128,61' : '47,107,255'},${alpha})`, dots };
  });
}
const BLUE_BANDS = makeBands(false);
const GREEN_BANDS = makeBands(true);
function DotField({ green = false }) {
  return <span className={`pr-field ${green ? 'pr-field-green' : ''}`} aria-hidden="true">
    {(green ? GREEN_BANDS : BLUE_BANDS).map((band, i) => <span className="pr-band" key={i} style={{ width: band.radius * 2, height: band.radius * 2, '--dx': `${10 + 3 * i}px`, '--dy': `${8 + 2.4 * i}px` }}>
      <span className="pr-breath" style={{ animationDelay: `${i * (green ? .16 : .32)}s` }}>
        {band.dots.map((dot, j) => <span key={j} style={{ ...dot, width: band.size, height: band.size, background: band.color, boxShadow: `0 0 6px ${band.color}` }} />)}
      </span>
    </span>)}
  </span>;
}
function CustomerAvatar({ thinking = false, large = false }) {
  return <span className={`pr-avatar ${large ? 'pr-avatar-large' : ''}`}>
    {thinking && <><span className="pr-ring" /><span className="pr-ring" /></>}KH
  </span>;
}
function CustomerContext({ session, scenario }) {
  const channel = session?.sales_channel || scenario?.sales_channel;
  const channels = { fanpage: 'Fanpage', showroom: 'Showroom', phone: 'điện thoại', hotline: 'Hotline', zalo: 'Zalo', online: 'trực tuyến' };
  const objective = session?.training_objective || scenario?.training_objective;
  return <div className="pr-context-content">
    {session?.visible_context && <section><h3>{channel ? `Khách nhắn qua ${channels[channel] || channel}` : 'Bối cảnh khách'}</h3><p>{session.visible_context}</p></section>}
    {objective && <section><h3>Mục tiêu</h3><p>{objective}</p></section>}
    <section><h3>Bạn được chấm theo 5 kỹ năng</h3><ol>{['Khám phá nhu cầu', 'Kiến thức sản phẩm', 'Xử lý phản đối', 'Chính xác chính sách', 'Chốt bước tiếp theo'].map((skill) => <li key={skill}>{skill}</li>)}</ol></section>
  </div>;
}
function Transcript({ messages, waiting, listRef, playCustomer, speakingId }) {
  const origin = Date.parse(messages[0]?.timestamp);
  return <ol className="pr-transcript" role="log" aria-label="Hội thoại" ref={listRef}>
    {!messages.length && <li>Bạn là tư vấn viên — hãy mở lời chào khách trước.</li>}
    {messages.map((message, i) => <li key={message.message_id || i} className={message.role === 'advisor' ? 'pr-transcript-advisor' : ''}>
      <strong>{message.role === 'advisor' ? 'Bạn' : 'Khách'}{message.timestamp && Number.isFinite(origin) && ` · ${clock(Math.max(0, Math.floor((Date.parse(message.timestamp) - origin) / 1000)))}`}</strong>
      <p>{message.content}</p>
      {message.role === 'customer' && <button className="pr-replay" onClick={() => playCustomer(message)} disabled={speakingId === message.message_id} aria-label="Phát giọng khách"><SpeakerIcon /></button>}
    </li>)}
    {waiting && <li role="status">Khách đang suy nghĩ…</li>}
  </ol>;
}

export function PracticeRoom({
  scenario,
  session,
  onFinish,
  onSavedAttempt,
  onExit,
  initialMode = 'text',
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
  const [limitToast, setLimitToast] = useState(null);
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
  const [mode, setMode] = useState(initialMode === 'voice' ? 'voice' : 'text');
  const [autoSendPreference, setAutoSendPreference] = useState(() => {
    try {
      const saved = initialMode === 'voice' ? 'true' : localStorage.getItem(VOICE_SEND_PREFERENCE_KEY);
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

  const chatListRef = useRef(null);
  const transcriptRef = useRef(null);
  const audioRef = useRef(null);
  const audioUrlsRef = useRef(new Map());
  const modeRef = useRef(mode);
  const sendingRef = useRef(false);
  const sendHandlerRef = useRef(null);

  useEffect(() => { modeRef.current = mode; }, [mode]);

  const onRecorded = async (blob, durationSeconds, reason) => {
    if (reason === 'limit') setLimitToast(Date.now());
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

  const camera = useLocalCamera();
  const [mirrorEnabled, setMirrorEnabled] = useState(false);
  const [mirrorLayout, setMirrorLayout] = useState(() => readPreference('practice.mirror.layout', 'split'));
  const [captionsOn, setCaptionsOn] = useState(() => readPreference('practice.mirror.captions', 'true') !== 'false');
  const toggleCaptions = () => setCaptionsOn((value) => { savePreference('practice.mirror.captions', String(!value)); return !value; });
  const [phone, setPhone] = useState(() => window.matchMedia('(max-width: 768px)').matches);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [callSeconds, setCallSeconds] = useState(0);
  const [slow, setSlow] = useState(false);
  const videoRef = useRef(null);
  const drawerRef = useRef(null);
  const drawerTriggerRef = useRef(null);
  const voiceStartedRef = useRef(null);
  const waiting = loading || pendingReply;
  const recording = recorder.recordingState === 'recording';
  const mirrorOn = mode === 'voice' && camera.status === 'on';
  const focusMirror = mirrorOn && (phone || mirrorLayout === 'focus');
  const thinking = waiting || transcribing;
  const micDisabled = loading || finishing || pendingReply || transcribing || speakingId !== null || terminationStatus !== 'active';
  const statusText = recording ? 'Đang nghe bạn' : thinking ? 'Đang suy nghĩ…' : speakingId ? 'Đang nói' : 'Sẵn sàng nghe bạn';
  const latestCustomer = messages.findLast((message) => message.role === 'customer');
  const latestAdvisor = messages.findLast((message) => message.role === 'advisor');
  const maxTurns = session?.max_turns || 10;
  const { start: startCamera, stop: stopCamera } = camera;
  useEffect(() => {
    const query = window.matchMedia('(max-width: 768px)');
    const update = () => setPhone(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (mode === 'voice' && mirrorEnabled && terminationStatus === 'active') startCamera();
    else stopCamera();
    return stopCamera;
  }, [mode, mirrorEnabled, startCamera, stopCamera, terminationStatus]);
  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = camera.stream;
  }, [camera.stream, focusMirror]);
  useEffect(() => {
    if (mode !== 'voice') return;
    voiceStartedRef.current = Date.now();
    const timer = setInterval(() => setCallSeconds(Math.floor((Date.now() - voiceStartedRef.current) / 1000)), 500);
    return () => clearInterval(timer);
  }, [mode]);
  useEffect(() => {
    const reset = setTimeout(() => setSlow(false), 0);
    const timer = waiting ? setTimeout(() => setSlow(true), 15000) : null;
    return () => { clearTimeout(reset); clearTimeout(timer); };
  }, [waiting]);
  useEffect(() => {
    if (!limitToast) return;
    const timer = setTimeout(() => setLimitToast(null), 4000);
    return () => clearTimeout(timer);
  }, [limitToast]);
  useEffect(() => {
    if (!drawerOpen) return;
    const previous = drawerTriggerRef.current;
    drawerRef.current?.querySelector('button')?.focus();
    return () => previous?.focus();
  }, [drawerOpen]);
  useEffect(() => {
    const stop = () => recorder.stop();
    window.addEventListener('blur', stop);
    return () => window.removeEventListener('blur', stop);
  }, [recorder]);
  useEffect(() => {
    const input = inputRef.current;
    if (input) { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 120)}px`; }
  }, [inputMessage, mode]);
  const toggleMirror = () => {
    const next = !mirrorEnabled || ['denied', 'error', 'unsupported'].includes(camera.status);
    setMirrorEnabled(next);
    if (next && mirrorEnabled) startCamera();
    if (!next) stopCamera();
  };
  const chooseLayout = (layout) => {
    setMirrorLayout(layout);
    savePreference('practice.mirror.layout', layout);
  };
  const parallax = (event) => {
    if (!window.matchMedia('(pointer: fine)').matches || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--mx', String(Math.max(-1, Math.min(1, (event.clientX - bounds.left) / bounds.width * 2 - 1))));
    event.currentTarget.style.setProperty('--my', String(Math.max(-1, Math.min(1, (event.clientY - bounds.top) / bounds.height * 2 - 1))));
  };
  const roomKeyDown = (event) => {
    if (event.key === 'Escape') setDrawerOpen(false);
  };
  // Space talks from anywhere on the page in voice mode, except while typing or when another control has focus.
  const spaceTalksFrom = (target) => {
    if (!(target instanceof Element)) return true;
    if (target.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]')) return false;
    const control = target.closest('button, a[href], summary');
    return !control || control.classList.contains('pr-mic');
  };
  const micRef = useRef(null);
  // Entering voice mode hands keyboard focus to the mic, so Space talks straight away.
  useEffect(() => {
    if (mode === 'voice') micRef.current?.focus({ preventScroll: true });
  }, [mode]);
  const spaceRef = useRef({});
  useEffect(() => {
    spaceRef.current = {
    down(event) {
      if (event.key !== ' ' || mode !== 'voice' || !spaceTalksFrom(event.target)) return;
      event.preventDefault();
      if (!event.repeat && !micDisabled && !showFinishConfirm && !notice && !drawerOpen) recorder.start();
    },
    up(event) {
      if (event.key !== ' ' || mode !== 'voice' || !spaceTalksFrom(event.target)) return;
      event.preventDefault();
      recorder.stop();
    },
    };
  });
  useEffect(() => {
    const onDown = (event) => spaceRef.current.down?.(event);
    const onUp = (event) => spaceRef.current.up?.(event);
    document.addEventListener('keydown', onDown);
    document.addEventListener('keyup', onUp);
    return () => {
      document.removeEventListener('keydown', onDown);
      document.removeEventListener('keyup', onUp);
    };
  }, []);

  const stageLabels = {
    opening: 'Giai đoạn: Chào hỏi & Mở đầu',
    discovery: 'Giai đoạn: Khai thác nhu cầu',
    presentation: 'Giai đoạn: Giới thiệu giải pháp',
    objection_handling: 'Giai đoạn: Xử lý băn khoăn',
    closing: 'Giai đoạn: Chốt & Hướng dẫn',
    completed: 'Giai đoạn: Hoàn thành',
  };

  useEffect(() => {
    for (const list of [chatListRef.current, transcriptRef.current]) {
      if (list) list.scrollTop = list.scrollHeight;
    }
  }, [messages, loading, mode, pendingReply, drawerOpen]);

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
      const request = practiceApi.sendMessage(session.session_id, text);
      setInputMessage('');
      const updated = await request;
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
        // Preserve any next-turn draft typed while waiting.
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
    setShowFinishConfirm(true);
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

  const context = <CustomerContext session={session} scenario={scenario} />;
  const modeControl = <div className="pr-segment pr-mode" role="group" aria-label="Cách luyện">
    {['text', 'voice'].map((value) => <button key={value} aria-pressed={mode === value} onClick={() => { if (mode !== value) { setCallSeconds(0); toggleVoiceMode(); } }} disabled={recorder.recordingState !== 'idle' || transcribing || terminationStatus !== 'active'}>{value === 'text' ? <><MessageCircle aria-hidden="true" />Nhắn tin</> : <><Phone aria-hidden="true" />Gọi thoại</>}</button>)}
  </div>;
  const layoutControl = <div className="pr-segment pr-layout" role="group" aria-label="Bố cục Mirror">
    <button aria-pressed={mirrorLayout === 'split'} onClick={() => chooseLayout('split')}>Chia đôi</button>
    <button aria-pressed={mirrorLayout === 'focus'} onClick={() => chooseLayout('focus')}>Toàn màn hình</button>
  </div>;
  const mic = <span className={`pr-mic-wrap ${recording ? 'pr-recording' : ''}`}>
    {recording && <DotField green />}
    <button ref={micRef} className="pr-mic" disabled={micDisabled} aria-label={autoSendPreference ? 'Bấm giữ để nói, thả để gửi' : 'Bấm giữ để nói, thả để chép vào ô nhập'} aria-pressed={recording}
      onPointerDown={(event) => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); recorder.start(); }}
      onPointerUp={() => recorder.stop()} onPointerLeave={() => recorder.stop()} onPointerCancel={() => recorder.stop()} onLostPointerCapture={() => recorder.stop()} onBlur={() => recorder.stop()}
      onKeyDown={(event) => { if (event.key === 'Enter' && !event.repeat && !micDisabled) { event.preventDefault(); recorder.start(); } }}
      onKeyUp={(event) => { if (event.key === 'Enter') { event.preventDefault(); recorder.stop(); } }}><MicIcon aria-hidden="true" /></button>
  </span>;
  const autoSendSwitch = <button className="pr-auto-send" role="switch" aria-checked={autoSendPreference} onClick={() => chooseAutoSend(!autoSendPreference)} disabled={waiting || finishing || transcribing || recorder.recordingState !== 'idle'}><span aria-hidden="true" />Tự động gửi</button>;
  const talkHint = <div className="pr-talk-hint"><strong>{recording ? (autoSendPreference ? 'Đang thu, thả để gửi' : 'Đang thu, thả để chép') : 'Giữ để nói'}</strong><span>Hoặc giữ phím Space.<br />{autoSendPreference ? 'Thả tay là gửi.' : 'Thả rồi kiểm tra bản chép.'}</span>{autoSendSwitch}</div>;
  const toast = limitToast && <div className="pr-toast" role="status"><Clock size={18} />{autoSendPreference ? 'Đã tự gửi vì mỗi lượt nói tối đa 90 giây.' : 'Đã dừng ghi âm vì mỗi lượt nói tối đa 90 giây.'}</div>;
  const transcript = <Transcript messages={messages} waiting={waiting} listRef={transcriptRef} playCustomer={playCustomer} speakingId={speakingId} />;
  const composer = <div className="pr-composer">
    <div className="pr-compose-row"><textarea ref={inputRef} value={inputMessage} onChange={(event) => setInputMessage(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); handleSendMessage(); } }} placeholder="Nhắn cho khách…" aria-label="Nhắn tin cho khách hàng" rows={1} disabled={finishing || transcribing || recorder.recordingState !== 'idle' || terminationStatus !== 'active'} />
      <button className="pr-send" onClick={() => handleSendMessage()} disabled={!inputMessage.trim() || waiting || finishing || transcribing || recorder.recordingState !== 'idle' || terminationStatus !== 'active'} aria-label="Gửi tin nhắn"><SendIcon /></button></div>
    <p className="pr-hint">{waiting ? 'Bạn vẫn gõ trước được. Nút gửi mở lại khi khách trả lời xong.' : 'Enter để gửi, Shift + Enter để xuống dòng.'}</p>
  </div>;
  const vehicleModel = /VF[\s_-]*(Wild|[356789])(?![a-z0-9])/i.exec(`${scenario?.model_badge || ''} ${scenario?.model || ''} ${scenario?.scenario_id || ''} ${scenario?.title || ''}`)?.[1].toLowerCase();
  const isApartmentScenario = scenario?.scenario_id === 'SCENARIO_03_VF6_APARTMENT';
  const vehicle = isApartmentScenario ? '/vehicles/official/vf-6-green.webp' : vehicleModel ? `/vehicles/official/vf-${vehicleModel}.webp` : getVehicleImage(scenario?.model_badge || scenario?.model || scenario?.title);
  const vehicleAlt = isApartmentScenario ? 'VinFast VF 6 màu xanh' : vehicleModel ? `VinFast VF ${vehicleModel === 'wild' ? 'Wild' : vehicleModel}` : 'Xe luyện tập';
  return (
    <section className={`pr-room ${mode === 'voice' ? 'pr-voice' : 'pr-text'} ${mirrorOn ? 'pr-mirror' : ''} ${focusMirror ? 'pr-focus' : ''}`} aria-label="Phiên luyện tập" onKeyDown={roomKeyDown}>
      <NoticeDialog notice={notice} onAction={handleNoticeAction} onClose={() => setNotice(null)} />
      <header className="pr-bar">
        <button className="pr-back" onClick={onExit} aria-label="Rời phòng"><ChevronLeft /><span>Rời phòng</span></button>
        {vehicle && <img className="pr-vehicle" src={vehicle} alt={vehicleAlt} width={200} height={106} />}
        <div className="pr-identity"><h2>{scenario?.title}</h2><div className="pr-meta"><span className="pr-model">{scenario?.model_badge || scenario?.model}</span><span className="pr-stage-label">{stageLabels[stage] || stage}</span><span>Lượt {turnCount} / {maxTurns}</span><progress aria-label="Tiến độ lượt trao đổi" value={turnCount} max={maxTurns} />{focusMirror && <span>Cuộc gọi {clock(callSeconds)}</span>}</div></div>
        {modeControl}
        {focusMirror && <><span className="pr-private"><ShieldCheck size={16} />Chỉ trên máy này</span>{layoutControl}<button className="pr-mirror-off" onClick={toggleMirror} aria-label="Tắt Mirror"><VideoOff size={18} /></button></>}
        <button className="pr-finish" onClick={() => setShowFinishConfirm(true)} disabled={waiting || finishing || transcribing || recorder.recordingState !== 'idle'}><span className="pr-finish-full">Kết thúc & chấm điểm</span><span className="pr-finish-short">Kết thúc</span></button>
        <details className="pr-phone-context"><summary>Bối cảnh khách ▾</summary>{context}</details>
      </header>
      {terminationStatus !== 'active' && <p className={`pr-termination ${terminationStatus === 'advisor_misconduct' ? 'pr-misconduct' : ''}`} role="status">{terminationStatus === 'advisor_misconduct' ? 'Phiên luyện tập đã dừng do ngôn từ không phù hợp.' : 'Cuộc trò chuyện đã kết thúc. Hãy xem đánh giá.'}</p>}
      <div className="pr-body">
        {mode === 'text' ? <>
          <aside className="pr-context" aria-label="Bối cảnh khách"><h2>Bối cảnh khách</h2>{context}</aside>
          <div className="pr-chat"><ol className="pr-messages" role="log" aria-label="Hội thoại" ref={chatListRef}>
            {!messages.length && <li className="pr-empty" role="status">Bạn là tư vấn viên.<br />Hãy mở lời chào khách trước.</li>}
            {messages.map((message, i) => <li key={message.message_id || i} className={`pr-message ${message.role === 'advisor' ? 'pr-advisor' : ''}`}>
              <span className="pr-message-avatar" aria-hidden="true">{message.role === 'advisor' ? 'TV' : 'KH'}</span><div className="pr-message-main"><div className="pr-message-meta"><strong>{message.role === 'advisor' ? 'Bạn' : 'Khách'}</strong>{message.timestamp && <><span>·</span><time dateTime={message.timestamp}>{new Date(message.timestamp).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</time></>}</div><div className="pr-bubble"><p>{message.content}</p>{message.role === 'customer' && <button className="pr-replay" onClick={() => playCustomer(message)} disabled={speakingId === message.message_id} aria-label="Phát giọng khách"><SpeakerIcon /></button>}</div>{message.role === 'advisor' && i === messages.length - 1 && <span className="pr-receipt">{waiting ? 'Đã xem' : 'Đã gửi'}</span>}</div>
            </li>)}
            {waiting && <li className="pr-message"><span className="pr-message-avatar" aria-hidden="true">KH</span><div><div className="pr-message-meta"><strong>Khách</strong> · đang soạn tin</div><span className="pr-typing" role="status" aria-label="Khách đang soạn tin"><i /><i /><i /></span></div></li>}
          </ol>{composer}</div>
        </> : <>
          <div className="pr-stage" onPointerMove={parallax} onPointerLeave={(event) => { event.currentTarget.style.setProperty('--mx', '0'); event.currentTarget.style.setProperty('--my', '0'); }}>
            {mirrorOn ? <>
              <video className="pr-video" ref={videoRef} autoPlay muted playsInline />
              {!focusMirror && <div className="pr-video-top"><span className="pr-private"><ShieldCheck size={18} />Mirror chỉ hiện trên máy này, không ghi hình</span>{layoutControl}<button onClick={toggleMirror}><VideoOff size={18} />Tắt Mirror</button></div>}
              <div className="pr-video-bottom">
                <div className="pr-customer-card"><CustomerAvatar thinking={thinking} /><div><strong>Khách</strong><span role="status">{statusText}</span></div></div>
                {focusMirror && captionsOn && <div className="pr-focus-caption" aria-live="polite"><p>{latestCustomer?.content || 'Phụ đề lời khách sẽ hiện ở đây khi khách nói.'}</p><small>Bạn: {recording ? <span className="pr-caret">…</span> : transcribing ? 'Đang chuyển giọng nói thành chữ…' : latestAdvisor?.content || 'giữ nút để trả lời'}</small></div>}
                <div className="pr-call-controls"><span className="pr-focus-tools"><button className="pr-caption-toggle" onClick={toggleCaptions} aria-pressed={captionsOn}>{captionsOn ? <CaptionsOff aria-hidden="true" /> : <Captions aria-hidden="true" />}{captionsOn ? 'Ẩn phụ đề' : 'Hiện phụ đề'}</button><button className="pr-drawer-trigger" ref={drawerTriggerRef} onClick={() => setDrawerOpen(true)} aria-expanded={drawerOpen}>Hội thoại ({messages.length})</button></span>{mic}{talkHint}<button className="pr-phone-text" onClick={toggleVoiceMode} disabled={recorder.recordingState !== 'idle' || transcribing}>Nhắn tin</button></div>
              </div>
            </> : <>
              <span className="pr-call-timer">Cuộc gọi luyện tập · {clock(callSeconds).padStart(5, '0')}</span>
              <div className="pr-avatar-area"><DotField /><div className="pr-parallax-avatar"><CustomerAvatar thinking={thinking} large /></div></div>
              <div className="pr-customer-name"><strong>Khách</strong><span role="status">{speakingId && <span className="pr-wave" aria-hidden="true">{[0, 1, 2, 3, 4].map((i) => <i key={i} style={{ animationDelay: `${i * .12}s` }} />)}</span>}{statusText}</span></div>
              <p className="pr-caption" aria-live="polite">{latestCustomer?.content || 'Phụ đề lời khách sẽ hiện ở đây khi khách nói.'}</p>
              <div className="pr-call-controls"><div className="pr-mirror-control"><button className="pr-mirror-enable" onClick={toggleMirror} disabled={camera.status === 'requesting' || terminationStatus !== 'active'}><span><strong>{camera.status === 'requesting' ? 'Đang mở camera…' : 'Bật Mirror'}</strong><small>Chỉ trên máy bạn, không ghi hình</small><em>Tập nụ cười và ánh mắt tự tin khi nói</em></span><span className="pr-camera-icon"><Video /></span></button>{['denied', 'unsupported', 'error'].includes(camera.status) && <p className="pr-camera-error" role="status">{camera.status === 'denied' ? 'Chưa có quyền dùng camera. Hãy cho phép camera trong trình duyệt.' : camera.status === 'unsupported' ? 'Trình duyệt không hỗ trợ camera.' : 'Không mở được camera. Hãy kiểm tra camera rồi thử lại.'}</p>}</div>{mic}{talkHint}</div>
            </>}
            {toast}
          </div>
          {!focusMirror && <details className="pr-transcript-panel" open={!phone}><summary>Hội thoại ({messages.length})</summary><details className="pr-voice-context"><summary>Bối cảnh khách và mục tiêu</summary>{context}</details><h2>{mirrorOn ? 'Toàn bộ hội thoại' : 'Hội thoại'}</h2>{transcript}{!autoSendPreference && composer}</details>}
        </>}
      </div>
      {(slow && waiting || pendingReply) && <div className="pr-slow" role="status"><span>{slow ? 'Khách đang cân nhắc lâu hơn thường lệ.' : 'Tin nhắn đã lưu. Khách hàng chưa phản hồi.'}</span>{pendingReply && <button onClick={handleRetryReply} disabled={loading || finishing || transcribing || recorder.recordingState !== 'idle'}>Gửi lại yêu cầu</button>}</div>}
      {(voiceHint || recorder.recordingError) && <p className="pr-feedback" role="status">{voiceHint || recorder.recordingError}</p>}
      {focusMirror && !autoSendPreference && inputMessage && <div className="pr-focus-draft">{composer}</div>}
      {drawerOpen && <div className="pr-drawer-backdrop" onClick={() => setDrawerOpen(false)}><aside className="pr-drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-label="Toàn bộ hội thoại" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => { if (event.key === 'Tab') { const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled)')]; const first = controls[0]; const last = controls.at(-1); if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } } }}><header><h2>Toàn bộ hội thoại</h2><button aria-label="Đóng hội thoại" onClick={() => setDrawerOpen(false)}><X /></button></header>{transcript}</aside></div>}
      <FinishConfirmDialog isOpen={showFinishConfirm} onClose={() => setShowFinishConfirm(false)} onConfirm={handleFinishSession} finishing={finishing} />
    </section>
  );
}
