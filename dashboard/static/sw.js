/* global caches, fetch, self */
const CACHE_NAME = 'hermes-v6';
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/splash.html',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

/** GET responses for these API paths are cached after a successful fetch for offline reread */
const API_CACHE_PATHS = ['/api/agents/pnl'];

function shouldCacheApiResponse(url) {
  const p = url.pathname;
  return API_CACHE_PATHS.some((prefix) => p === prefix || p.startsWith(prefix + '?'));
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) =>
        Promise.all(
          STATIC_ASSETS.map((url) =>
            cache.add(new Request(url, { cache: 'reload' })).catch(() => {}),
          ),
        ),
      )
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // HTML navigations: network-first so login UI / templates update without stale cache.
  if (req.mode === 'navigate' || req.destination === 'document') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => caches.match(req)),
    );
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && shouldCacheApiResponse(url)) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => caches.match(req)),
    );
    return;
  }

  if (url.pathname === '/sw.js') {
    event.respondWith(fetch(req));
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        const copy = res.clone();
        if (res.ok && url.pathname.startsWith('/static/')) {
          caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      });
    }),
  );
});

// Placeholder for future Web Push (requires app server + VAPID).
self.addEventListener('push', (event) => {
  let data = { title: 'LETAGENTSCOOK', body: 'Update' };
  try {
    if (event.data) data = { ...data, ...event.json() };
  } catch (_) {
    if (event.data) data.body = event.data.text();
  }
  event.waitUntil(self.registration.showNotification(data.title, { body: data.body, icon: '/static/icons/icon-192.png' }));
});
