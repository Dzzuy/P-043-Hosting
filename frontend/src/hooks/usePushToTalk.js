import { useEffect, useRef, useState } from 'react';

const MAX_RECORDING_MS = 90_000;
const FORMATS = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm'];

export function usePushToTalk(onRecorded) {
  const [recordingState, setRecordingState] = useState('idle');
  const [recordingError, setRecordingError] = useState('');
  const [permissionError, setPermissionError] = useState(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const startedAtRef = useRef(0);
  const timerRef = useRef(null);
  const pendingStopRef = useRef(false);
  const failedRef = useRef(false);
  const mountedRef = useRef(true);
  const onRecordedRef = useRef(onRecorded);

  useEffect(() => {
    onRecordedRef.current = onRecorded;
  }, [onRecorded]);

  const release = () => {
    clearTimeout(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  };

  const stop = () => {
    pendingStopRef.current = true;
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
  };

  const start = async () => {
    if (recorderRef.current || recordingState !== 'idle') return;
    setRecordingError('');
    setPermissionError(null);
    setRecordingState('requesting');
    pendingStopRef.current = false;
    failedRef.current = false;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setRecordingError('Trình duyệt này không hỗ trợ ghi âm. Hãy dùng Chế độ chữ.');
      setRecordingState('idle');
      return;
    }
    try {
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (error) {
        if (['NotAllowedError', 'NotFoundError'].includes(error.name)) setPermissionError(error);
        throw error;
      }
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const mimeType = FORMATS.find((format) => MediaRecorder.isTypeSupported?.(format));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      if (!['audio/webm', 'audio/mp4', 'audio/ogg', 'audio/wav'].includes(recorder.mimeType.split(';')[0])) {
        throw new Error('Trình duyệt không có định dạng âm thanh phù hợp. Hãy dùng Chế độ chữ.');
      }
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        failedRef.current = true;
        setRecordingError('Ghi âm bị gián đoạn. Vui lòng thử lại.');
        release();
        setRecordingState('idle');
      };
      recorder.onstop = () => {
        const durationSeconds = (Date.now() - startedAtRef.current) / 1000;
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        release();
        if (!mountedRef.current || failedRef.current) return;
        setRecordingState('idle');
        if (blob.size && durationSeconds >= 0.1) {
          onRecordedRef.current(blob, Math.min(durationSeconds, MAX_RECORDING_MS / 1000));
        } else {
          setRecordingError('Không có âm thanh. Giữ nút nói lâu hơn rồi thử lại.');
        }
      };
      startedAtRef.current = Date.now();
      recorder.start();
      setRecordingState('recording');
      timerRef.current = setTimeout(stop, MAX_RECORDING_MS);
      if (pendingStopRef.current) stop();
    } catch (error) {
      release();
      setRecordingState('idle');
      setRecordingError(error.name === 'NotAllowedError'
        ? 'Micro chưa được cho phép. Hãy bật quyền micro trong trình duyệt rồi thử lại.'
        : error.message || 'Không thể ghi âm. Vui lòng thử lại.');
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimeout(timerRef.current);
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  return { recordingState, recordingError, permissionError, start, stop };
}
