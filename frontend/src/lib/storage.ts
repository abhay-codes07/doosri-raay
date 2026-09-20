/** localStorage helpers that never throw (private mode, quota, disabled storage). */

export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

export function readString(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeString(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

export function remove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

/** Remove every key with the given prefix. */
export function removePrefix(prefix: string): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const k = localStorage.key(i);
      if (k && k.startsWith(prefix)) keys.push(k);
    }
    keys.forEach((k) => localStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}

export const KEYS = {
  prefix: 'dr:',
  pact: (id: string) => `dr:${id}:pact`,
  checkinDay: (id: string) => `dr:${id}:checkin`,
  meds: (id: string, day: string) => `dr:${id}:meds:${day}`,
  reports: (id: string) => `dr:${id}:reports`,
  previews: 'dr:previews',
  geocode: (city: string) => `dr:geo:${city.toLowerCase()}`,
  weather: (city: string) => `dr:wx:${city.toLowerCase()}`,
  pushDone: (id: string) => `dr:${id}:push`,
  pendingSos: (id: string) => `dr:${id}:sos`,
} as const;

/** Local screenshot previews keyed by objectKey (data URLs, small). */
export function savePreview(objectKey: string, dataUrl: string): void {
  const map = readJson<Record<string, string>>(KEYS.previews, {});
  map[objectKey] = dataUrl;
  // keep at most 12 previews to stay under quota
  const keys = Object.keys(map);
  if (keys.length > 12) keys.slice(0, keys.length - 12).forEach((k) => delete map[k]);
  writeJson(KEYS.previews, map);
}

export function getPreview(objectKey: string): string | null {
  return readJson<Record<string, string>>(KEYS.previews, {})[objectKey] ?? null;
}

export interface ReportRef {
  reportId: string;
  createdAt: string;
  label: string;
}

/** Dashboard mount fetches every remembered report, so keep the list short. */
export const MAX_REMEMBERED_REPORTS = 5;

export function rememberReport(identity: string, ref: ReportRef): void {
  const list = readJson<ReportRef[]>(KEYS.reports(identity), []);
  writeJson(KEYS.reports(identity), [ref, ...list.filter((r) => r.reportId !== ref.reportId)].slice(0, MAX_REMEMBERED_REPORTS));
}

export function listReports(identity: string): ReportRef[] {
  return readJson<ReportRef[]>(KEYS.reports(identity), []).slice(0, MAX_REMEMBERED_REPORTS);
}
