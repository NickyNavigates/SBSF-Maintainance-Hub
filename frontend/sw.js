// Minimal service worker: app-shell cache so the UI loads offline.
// API responses are always fetched fresh (network-first, no caching).
const CACHE = "sbsf-hub-v1";
const SHELL = ["/", "/index.html", "/styles.css", "/app.js", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // never cache API
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
