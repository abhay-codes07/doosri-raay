import type { SourceEntry } from '../api/types';

/** Stable anchor for a source entry (case cards link here). */
export function sourceAnchor(src: SourceEntry): string {
  return `src-${(src.sha256 ?? '').slice(0, 8) || encodeURIComponent(src.url).slice(0, 16)}`;
}

/** Same document regardless of scheme/trailing slash/#fragment. */
export function normalizeUrl(u: string | undefined): string {
  if (!u) return '';
  return u
    .trim()
    .replace(/^https?:\/\//i, '')
    .replace(/#.*$/, '')
    .replace(/\/+$/, '')
    .toLowerCase();
}

export function findSource(sources: SourceEntry[] | null, url: string | undefined): SourceEntry | undefined {
  const key = normalizeUrl(url);
  if (!key || !sources) return undefined;
  return sources.find((s) => normalizeUrl(s.url) === key);
}
