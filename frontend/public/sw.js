const CACHE_NAME = "hermes-v2";
const API_CACHE_TTL_MS = 5 * 60 * 1000;
const CORE_ASSETS = ["/", "/index.html"];
const API_ENDPOINTS = ["/api/agents/pnl", "/api/marketplace/agents"];

function isApiRequest(url) {
  return API_ENDPOINTS.some((endpoint) => url.pathname.startsWith(endpoint));
}

async function stampResponse(response, extraHeaders = {}) {
  const body = await response.clone().blob();
  const headers = new Headers(response.headers);
  headers.set("sw-fetched-at", String(Date.now()));
  Object.entries(extraHeaders).forEach(([key, value]) => headers.set(key, value));
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function isFresh(cached) {
  if (!cached) return false;
  const fetchedAt = Number(cached.headers.get("sw-fetched-at") || 0);
  if (!fetchedAt) return false;
  return Date.now() - fetchedAt <= API_CACHE_TTL_MS;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key)),
      ),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const requestUrl = new URL(event.request.url);

  if (isApiRequest(requestUrl)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(CACHE_NAME);
        try {
          const networkResponse = await fetch(event.request);
          if (networkResponse && networkResponse.status === 200) {
            const stamped = await stampResponse(networkResponse);
            await cache.put(event.request, stamped.clone());
          }
          return networkResponse;
        } catch {
          const cached = await cache.match(event.request);
          if (cached && isFresh(cached)) {
            return stampResponse(cached, { "x-hermes-offline-cached": "1" });
          }
          if (cached) {
            return stampResponse(cached, { "x-hermes-offline-cached": "1", "x-hermes-cache-stale": "1" });
          }
          return new Response(JSON.stringify({ offline: true, message: "Ste offline — zobrazujem cachované dáta", items: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json", "x-hermes-offline-cached": "1" },
          });
        }
      })(),
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;

      return fetch(event.request).then((response) => {
        if (!response || response.status !== 200 || response.type !== "basic") {
          return response;
        }
        const isStaticAsset =
          requestUrl.pathname === "/" ||
          requestUrl.pathname === "/index.html" ||
          requestUrl.pathname.endsWith(".js") ||
          requestUrl.pathname.endsWith(".css");
        if (isStaticAsset) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      });
    }),
  );
});
