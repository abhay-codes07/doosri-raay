import type { Medicine } from '../api/types';

/**
 * The API stores medicines as {name, time}. Older profiles (and hand-edited rows) may still hold
 * plain strings or partial objects; normalise everything to the object shape so no screen crashes.
 */
export function normalizeMedicines(value: unknown): Medicine[] {
  if (!Array.isArray(value)) return [];
  const out: Medicine[] = [];
  for (const item of value) {
    if (typeof item === 'string') {
      const name = item.trim();
      if (name) out.push({ name, time: '' });
    } else if (typeof item === 'object' && item !== null) {
      const o = item as { name?: unknown; time?: unknown };
      const name = typeof o.name === 'string' ? o.name.trim() : '';
      const time = typeof o.time === 'string' ? o.time.trim() : '';
      if (name) out.push({ name, time });
    }
  }
  return out;
}
