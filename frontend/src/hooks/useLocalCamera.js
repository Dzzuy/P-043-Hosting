import { useCallback, useEffect, useRef, useState } from 'react';

// A generation token releases streams that resolve after stop/unmount or a newer request.
export function useLocalCamera() {
  const [stream, setStream] = useState(null);
  const [status, setStatus] = useState('off');
  const streamRef = useRef(null);
  const generationRef = useRef(0);
  const stop = useCallback(() => {
    generationRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
    setStatus('off');
  }, []);
  const start = useCallback(async () => {
    if (streamRef.current) return;
    const generation = ++generationRef.current;
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('unsupported');
      return;
    }
    setStatus('requesting');
    try {
      const next = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
      if (generation !== generationRef.current) {
        next.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = next;
      setStream(next);
      setStatus('on');
    } catch (error) {
      if (generation !== generationRef.current) return;
      setStatus(['NotAllowedError', 'SecurityError'].includes(error.name) ? 'denied' : 'error');
    }
  }, []);
  useEffect(() => () => {
    generationRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);
  return { stream, status, start, stop };
}
