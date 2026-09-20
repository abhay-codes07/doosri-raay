import { useEffect, useState } from 'react';
import { useApi } from '../api/context';
import type { DemoConfig } from '../api/types';

/** Module-level cache: GET /demo/config never changes during a session and several cards read it. */
let cached: DemoConfig | null = null;
let inflight: Promise<DemoConfig> | null = null;

export function useDemoConfig(): DemoConfig | null {
  const api = useApi();
  const [config, setConfig] = useState<DemoConfig | null>(cached);
  useEffect(() => {
    if (cached) return undefined;
    let alive = true;
    inflight ??= api.getDemoConfig().then((c) => {
      cached = c;
      return c;
    });
    inflight
      .then((c) => alive && setConfig(c))
      .catch(() => {
        inflight = null;
      });
    return () => {
      alive = false;
    };
  }, [api]);
  return config;
}

export type WaitStep = 'watch' | 'rung' | 'confirm' | 'call1930' | 'ncrp' | 'mrm';

/** Seconds the workflow waits at a step, from the flat fields or the `timeouts` map; null when unknown. */
export function waitSeconds(config: DemoConfig | null, step: WaitStep): number | null {
  if (!config) return null;
  const flat: Record<WaitStep, number | null | undefined> = {
    watch: config.watchDeadlineSeconds,
    rung: config.rungTimeoutSeconds ?? config.timeouts?.rung,
    confirm: config.confirmSeconds ?? config.timeouts?.confirm,
    call1930: config.call1930Seconds ?? config.timeouts?.call1930,
    ncrp: config.ncrpSeconds ?? config.timeouts?.ncrp,
    mrm: config.mrmSeconds ?? config.timeouts?.mrm,
  };
  const v = flat[step];
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null;
}

/** Case status → the timer that is running while the case sits there. */
export function stepForStatus(status: string): WaitStep | null {
  switch (status) {
    case 'awaiting_confirmation':
      return 'confirm';
    case 'awaiting_1930':
      return 'call1930';
    case 'awaiting_ncrp':
      return 'ncrp';
    case 'mrm':
      return 'mrm';
    default:
      return null;
  }
}
