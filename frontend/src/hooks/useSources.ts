import { useEffect, useState } from 'react';
import { useApi } from '../api/context';
import { describeError } from '../api/client';
import type { SourcesResponse } from '../api/types';

/** GET /sources is static per deployment: fetched once, shared by the dashboard, case page and /try. */
let cached: SourcesResponse | null = null;
let inflight: Promise<SourcesResponse> | null = null;

export function useSources(): { data: SourcesResponse | null; error: string | null; loading: boolean } {
  const api = useApi();
  const [data, setData] = useState<SourcesResponse | null>(cached);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (cached) return undefined;
    let alive = true;
    inflight ??= api.getSources().then((r) => {
      cached = r;
      return r;
    });
    inflight
      .then((r) => alive && setData(r))
      .catch((e: unknown) => {
        inflight = null;
        if (alive) setError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, [api]);
  return { data, error, loading: !data && !error };
}
