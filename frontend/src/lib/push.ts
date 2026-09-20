import type { ApiClient } from '../api/client';

export type PushSupport = 'supported' | 'unsupported' | 'ios_needs_install';

export function pushSupport(): PushSupport {
  if (typeof window === 'undefined') return 'unsupported';
  const hasApis = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  if (hasApis) return 'supported';
  const isIos = /iP(hone|ad|od)/.test(navigator.userAgent);
  const standalone = window.matchMedia('(display-mode: standalone)').matches;
  if (isIos && !standalone) return 'ios_needs_install';
  return 'unsupported';
}

export function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const buf = new ArrayBuffer(raw.length);
  const out = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

export type EnablePushResult =
  | { ok: true }
  | { ok: false; reason: 'denied' | 'unsupported' | 'no_key' | 'error'; detail?: string };

/**
 * Request permission, subscribe with the VAPID key and register the subscription with the API.
 */
export async function enablePush(api: ApiClient): Promise<EnablePushResult> {
  if (pushSupport() !== 'supported') return { ok: false, reason: 'unsupported' };
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') return { ok: false, reason: 'denied' };

    let key = (import.meta.env.VITE_VAPID_PUBLIC_KEY ?? '').trim();
    if (!key) {
      const r = await api.getPushPublicKey();
      key = (r.publicKey ?? '').trim();
    }
    if (!key) return { ok: false, reason: 'no_key' };

    // `ready` never settles when no worker is registered (dev, blocked SW): race it with 3 s.
    const reg = await Promise.race<ServiceWorkerRegistration>([
      navigator.serviceWorker.ready,
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error('service worker not ready')), 3000)),
    ]);
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key),
      });
    }
    await api.pushSubscribe(sub.toJSON());
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: 'error', detail: e instanceof Error ? e.message : String(e) };
  }
}
