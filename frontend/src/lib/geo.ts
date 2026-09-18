/**
 * Last-known-position cache for the covert SOS.
 *
 * Permission is asked once, during onboarding (parent role), never at SOS time: a permission
 * prompt in the middle of a triple-tap would give the gesture away. The parent tile keeps a
 * `watchPosition` running while it is open so that an SOS can be posted at once with whatever
 * fix we already have (accuracy -1 when there is none).
 */

export interface LastPosition {
  lat: number;
  lon: number;
  accuracy: number;
  at: number;
}

let last: LastPosition | null = null;
let watchId: number | null = null;

export const hasGeolocation = (): boolean => typeof navigator !== 'undefined' && 'geolocation' in navigator;

function remember(pos: GeolocationPosition): void {
  last = {
    lat: pos.coords.latitude,
    lon: pos.coords.longitude,
    accuracy: Math.round(pos.coords.accuracy),
    at: Date.now(),
  };
}

/** The most recent fix, or null. Never triggers a permission prompt. */
export function lastKnownPosition(): LastPosition | null {
  return last;
}

/** What POST /sos should carry right now: the cached fix, or accuracy -1 when there is none. */
export function sosLocation(): { lat: number; lon: number; accuracy: number } {
  return last ? { lat: last.lat, lon: last.lon, accuracy: last.accuracy } : { lat: 0, lon: 0, accuracy: -1 };
}

/**
 * Start (or keep) a background watch. Safe to call repeatedly. Returns a stop function that only
 * stops the watch when the last subscriber leaves, so the demo page can mount two tiles.
 */
let subscribers = 0;
export function startPositionWatch(): () => void {
  if (!hasGeolocation()) return () => undefined;
  subscribers += 1;
  if (watchId === null) {
    try {
      // one quick low-accuracy fix first, then the continuous watch
      navigator.geolocation.getCurrentPosition(remember, () => undefined, { maximumAge: 5 * 60 * 1000, timeout: 10000 });
      watchId = navigator.geolocation.watchPosition(remember, () => undefined, {
        enableHighAccuracy: false,
        maximumAge: 60000,
      });
    } catch {
      watchId = null;
    }
  }
  return () => {
    subscribers = Math.max(0, subscribers - 1);
    if (subscribers === 0 && watchId !== null) {
      try {
        navigator.geolocation.clearWatch(watchId);
      } catch {
        /* ignore */
      }
      watchId = null;
    }
  };
}

export type GeoPermission = 'granted' | 'denied' | 'unavailable';

/**
 * Ask for location permission now (onboarding, behind an explicit button). Resolves with the
 * outcome; a granted fix is cached immediately.
 */
export function requestGeoPermission(): Promise<GeoPermission> {
  if (!hasGeolocation()) return Promise.resolve('unavailable');
  return new Promise((resolve) => {
    try {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          remember(pos);
          resolve('granted');
        },
        (err) => resolve(err.code === err.PERMISSION_DENIED ? 'denied' : 'unavailable'),
        { timeout: 15000, maximumAge: 0 },
      );
    } catch {
      resolve('unavailable');
    }
  });
}

/** Current permission state via the Permissions API when available (no prompt). */
export async function geoPermissionState(): Promise<PermissionState | 'unknown'> {
  try {
    if (!('permissions' in navigator)) return 'unknown';
    const st = await navigator.permissions.query({ name: 'geolocation' });
    return st.state;
  } catch {
    return 'unknown';
  }
}

/**
 * Run `fn` up to `attempts` times with exponential backoff (1 s, 3 s, 9 s). Never throws;
 * resolves true on the first success. Used to deliver an SOS in the background.
 */
export async function retryInBackground(fn: () => Promise<unknown>, attempts = 3, baseMs = 1000): Promise<boolean> {
  for (let i = 0; i < attempts; i += 1) {
    try {
      await fn();
      return true;
    } catch {
      if (i === attempts - 1) return false;
      await new Promise((r) => setTimeout(r, baseMs * 3 ** i));
    }
  }
  return false;
}
