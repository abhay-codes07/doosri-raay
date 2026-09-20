const IST_OFFSET_MS = 5.5 * 3600 * 1000;

/** YYYY-MM-DD of the given instant in IST. */
export function istDateString(now: Date = new Date()): string {
  const ist = new Date(now.getTime() + IST_OFFSET_MS);
  const y = ist.getUTCFullYear();
  const m = String(ist.getUTCMonth() + 1).padStart(2, '0');
  const d = String(ist.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function formatDateHi(now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('hi-IN', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    }).format(now);
  } catch {
    return now.toDateString();
  }
}

export function formatDateEn(now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('en-IN', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    }).format(now);
  } catch {
    return now.toDateString();
  }
}

/** "18 Sep, 11:05 am" in IST for an ISO string; returns '' for invalid input. */
export function formatTimeIST(iso: string | undefined | null, lang: 'hi' | 'en' = 'en'): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  try {
    return new Intl.DateTimeFormat(lang === 'hi' ? 'hi-IN' : 'en-IN', {
      day: 'numeric',
      month: 'short',
      hour: 'numeric',
      minute: '2-digit',
      timeZone: 'Asia/Kolkata',
    }).format(d);
  } catch {
    return d.toISOString();
  }
}

export function relativeTime(iso: string | undefined | null, lang: 'hi' | 'en' = 'en'): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diffMin = Math.round((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return lang === 'hi' ? 'अभी' : 'just now';
  if (diffMin < 60) return lang === 'hi' ? `${diffMin} मिनट पहले` : `${diffMin} min ago`;
  const h = Math.round(diffMin / 60);
  if (h < 24) return lang === 'hi' ? `${h} घंटे पहले` : `${h} h ago`;
  const days = Math.round(h / 24);
  return lang === 'hi' ? `${days} दिन पहले` : `${days} d ago`;
}

/** Seconds remaining until an ISO timestamp (never negative). */
export function secondsUntil(iso: string | undefined | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.round((t - Date.now()) / 1000));
}

/** Day-of-year index used to rotate the daily thought. */
export function dayOfYearIST(now: Date = new Date()): number {
  const ist = new Date(now.getTime() + IST_OFFSET_MS);
  const start = Date.UTC(ist.getUTCFullYear(), 0, 1);
  return Math.floor((ist.getTime() - start) / 86400000);
}

/** ISO timestamp → "YYYY-MM-DDTHH:mm" in IST for a datetime-local input ('' when unparseable). */
export function datetimeLocalFromIso(iso: string | undefined | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const ist = new Date(d.getTime() + IST_OFFSET_MS);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${ist.getUTCFullYear()}-${p(ist.getUTCMonth() + 1)}-${p(ist.getUTCDate())}T${p(ist.getUTCHours())}:${p(ist.getUTCMinutes())}`;
}

/** "YYYY-MM-DDTHH:mm[:ss]" from a datetime-local input, read as IST → ISO with +05:30 ('' when invalid). */
export function isoFromDatetimeLocal(local: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local.trim());
  if (!m) return '';
  const [, y, mo, d, h, mi, sec = '00'] = m;
  const probe = Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(sec));
  if (Number.isNaN(probe)) return '';
  return `${y}-${mo}-${d}T${h}:${mi}:${sec}+05:30`;
}
