import { useCallback, useEffect, useRef, useState } from 'react';

const cache = new Map();
const pending = new Map();
let epoch = 0;
export const CHANGE_EVENT = 'sales-workspace-changed';
export function notifyAgendaChange() {
  epoch += 1;
  cache.clear();
  pending.clear();
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(CHANGE_EVENT));
}
export function useAgendaResource(owner, key, fetcher, active = true) {
  const cacheKey = `${owner}:${key}`;
  const fetchRef = useRef(fetcher);
  useEffect(() => { fetchRef.current = fetcher; }, [fetcher]);
  const [state, setState] = useState(() => ({ key: cacheKey, data: cache.get(cacheKey)?.data, loading: false, error: '' }));
  const generation = useRef(0);
  const load = useCallback(async (force = false) => {
    const requestGeneration = ++generation.current;
    const cached = cache.get(cacheKey);
    if (!force && cached && Date.now() - cached.at < 30000) {
      setState({ key: cacheKey, data: cached.data, loading: false, error: '' }); return;
    }
    setState((previous) => ({ key: cacheKey, data: previous.key === cacheKey ? previous.data : cached?.data, loading: true, error: '' }));
    try {
      if (!pending.has(cacheKey)) {
        const started = epoch;
        const promise = fetchRef.current().then((data) => { if (started === epoch) cache.set(cacheKey, { data, at: Date.now() }); return data; }).finally(() => { if (pending.get(cacheKey) === promise) pending.delete(cacheKey); });
        pending.set(cacheKey, promise);
      }
      const data = await pending.get(cacheKey);
      if (generation.current === requestGeneration) setState({ key: cacheKey, data, loading: false, error: '' });
    } catch (error) {
      if (generation.current === requestGeneration) setState((previous) => ({ ...previous, loading: false, error: error.message || 'Chưa tải được dữ liệu.' }));
    }
  }, [cacheKey]);
  useEffect(() => {
    if (!active) return;
    void load();
    const refresh = () => { void load(true); };
    window.addEventListener(CHANGE_EVENT, refresh);
    return () => { generation.current += 1; window.removeEventListener(CHANGE_EVENT, refresh); };
  }, [load, active]);
  return { ...state, data: state.key === cacheKey ? state.data : cache.get(cacheKey)?.data, reload: () => load(true) };
}
