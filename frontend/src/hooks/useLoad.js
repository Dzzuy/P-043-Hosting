import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Load async data keyed by a primitive. Re-runs when `key` changes or `reload()` is called.
 * Stale data stays visible while a reload is in flight.
 */
export function useLoad(loader, key = '', fallbackError = 'Không thể tải dữ liệu.') {
  const [reloads, setReloads] = useState(0);
  const [result, setResult] = useState(null);
  const loaderRef = useRef(loader);
  const token = `${key}#${reloads}`;

  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    let ignore = false;
    loaderRef.current().then(
      (data) => { if (!ignore) setResult({ token, data, error: '' }); },
      (cause) => { if (!ignore) setResult({ token, data: null, error: cause?.message || fallbackError }); },
    );
    return () => { ignore = true; };
  }, [token, fallbackError]);

  const reload = useCallback(() => setReloads((value) => value + 1), []);
  const settled = result?.token === token;
  let status = 'loading';
  if (settled) status = result.error ? 'error' : 'ready';
  else if (result?.data != null) status = 'ready';
  return { status, data: result?.data ?? null, error: settled ? result.error : '', reload, setData: (updater) => setResult((current) => (current ? { ...current, data: typeof updater === 'function' ? updater(current.data) : updater } : current)) };
}
