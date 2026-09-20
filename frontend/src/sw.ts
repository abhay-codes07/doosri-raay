/// <reference lib="webworker" />
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute, NavigationRoute } from 'workbox-routing';
import { createHandlerBoundToURL } from 'workbox-precaching';
import { clientsClaim } from 'workbox-core';

declare let self: ServiceWorkerGlobalScope;

// autoUpdate mode: a new build must take over open tabs at once, otherwise a judge with the app
// open keeps the previous build until every tab is closed.
void self.skipWaiting();
clientsClaim();

cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

// SPA navigation fallback (only for same-origin navigations, never for the API).
try {
  registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html')));
} catch {
  /* index.html not in precache during dev */
}

interface PushPayload {
  title?: string;
  body?: string;
  taskId?: string;
  url?: string;
}

function parsePayload(event: PushEvent): PushPayload {
  if (!event.data) return {};
  try {
    const parsed: unknown = event.data.json();
    if (typeof parsed === 'object' && parsed !== null) return parsed as PushPayload;
  } catch {
    /* fall through to text */
  }
  try {
    return { body: event.data.text() };
  } catch {
    return {};
  }
}

self.addEventListener('push', (event: PushEvent) => {
  const payload = parsePayload(event);
  const title = payload.title ?? 'Doosri Raay';
  const body = payload.body ?? 'Parivaar ka kaam hai — app kholein.';
  const url = payload.url ?? '/guardian';
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      tag: payload.taskId ?? 'doosri-raay',
      requireInteraction: true,
      data: { url, taskId: payload.taskId },
    }),
  );
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  const data = (event.notification.data ?? {}) as { url?: string };
  const target = new URL(data.url ?? '/guardian', self.location.origin).href;
  event.waitUntil(
    (async () => {
      // Prefer a window this worker already controls (same origin, in-app navigation works there);
      // otherwise open a fresh window rather than hijacking an unrelated tab.
      const controlled = await self.clients.matchAll({ type: 'window', includeUncontrolled: false });
      const client = controlled.find((c) => c.url.startsWith(self.location.origin));
      if (client) {
        try {
          await client.focus();
          if (client.url !== target) await client.navigate(target);
          return;
        } catch {
          /* fall through to a new window */
        }
      }
      await self.clients.openWindow(target);
    })(),
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') void self.skipWaiting();
});
