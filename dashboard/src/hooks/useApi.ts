import { useEffect, useRef, useState } from "react";
import type { ApiResult } from "../lib/api";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Minimal data-fetching hook. Keeps the previous result on reload so the
 * UI never flickers to a skeleton when the user just toggles a filter. */
export function useApi<T>(fn: () => Promise<ApiResult<T>>, deps: unknown[] = []): AsyncState<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [tick, setTick] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    fn().then((res) => {
      if (!mounted.current) return;
      if (res.ok) {
        setState({ data: res.data, error: null, loading: false });
      } else {
        setState((s) => ({ data: s.data, error: res.error, loading: false }));
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}

/** Re-runs an API call on a polling interval; still returns the same shape. */
export function usePolling<T>(
  fn: () => Promise<ApiResult<T>>,
  intervalMs = 15_000,
  deps: unknown[] = []
): AsyncState<T> {
  const state = useApi(fn, deps);
  useEffect(() => {
    const id = window.setInterval(state.reload, intervalMs);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
  return state;
}
