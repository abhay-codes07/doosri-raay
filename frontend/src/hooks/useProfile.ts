import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../api/context';
import { describeError } from '../api/client';
import type { ProfileResponse } from '../api/types';

export interface ProfileState {
  data: ProfileResponse | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

/** Loads GET /profile once (and on demand). */
export function useProfile(enabled = true): ProfileState {
  const api = useApi();
  const [data, setData] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const load = useCallback(
    () =>
      api
        .getProfile()
        .then((r) => {
          if (alive.current) {
            setData(r);
            setError(null);
          }
        })
        .catch((e: unknown) => {
          if (alive.current) setError(describeError(e));
        })
        .finally(() => {
          if (alive.current) setLoading(false);
        }),
    [api],
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    await load();
  }, [load]);

  useEffect(() => {
    alive.current = true;
    if (enabled) void load();
    return () => {
      alive.current = false;
    };
  }, [enabled, load]);

  return { data, loading, error, reload };
}

/** Generic polling hook: runs `fn` every `intervalMs` while mounted (and tab visible). */
export function usePoll<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  deps: ReadonlyArray<unknown>,
  enabled = true,
): { data: T | null; error: string | null; loading: boolean; refresh: () => Promise<void> } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });

  const refresh = useCallback(async () => {
    try {
      const r = await fnRef.current();
      setData(r);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    let stopped = false;
    let timer: number | undefined;
    const tick = async () => {
      if (stopped) return;
      if (document.visibilityState === 'visible') await refresh();
      if (!stopped) timer = window.setTimeout(tick, intervalMs);
    };
    void tick();
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs, refresh, ...deps]);

  return { data, error, loading, refresh };
}
