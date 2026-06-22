// Minimal service worker: cache the app shell so the Archive launches instantly
// from the iPhone home screen, even on a flaky connection.
const CACHE = "companion-v1";
const SHELL = ["/", "/static/classic.html", "/static/manifest.webmanifest", "/static/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache API calls — always hit the live brain.
  if (url.pathname.startsWith("/chat") || url.pathname.startsWith("/memory") ||
      url.pathname.startsWith("/voice") || url.pathname.startsWith("/integrations") ||
      url.pathname === "/health") {
    return;
  }
  // Cache-first for the shell + CDN assets; fall back to network.
  e.respondWith(
    caches.match(e.request).then((hit) =>
      hit || fetch(e.request).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
        return resp;
      }).catch(() => hit)
    )
  );
});
