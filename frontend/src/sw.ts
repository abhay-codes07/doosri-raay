/// <reference lib="webworker" />
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute, NavigationRoute } from 'workbox-routing';
import { createHandlerBoundToURL } from 'workbox-precaching';

declare let self: ServiceWorkerGlobalScope;

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
      const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const client of clients) {
        if ('focus' in client) {
          await client.focus();
          if ('navigate' in client && client.url !== target) {
            try {
              await client.navigate(target);
            } catch {
              /* ignore */
            }
          }
          return;
        }
      }
      await self.clients.openWindow(target);
    })(),
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') void self.skipWaiting();
});
