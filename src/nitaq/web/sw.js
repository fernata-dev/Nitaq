// Offline support. Network first (so updates show at once), cached copy when offline.
// Only the app's own files are cached. /api/* (desktop mode) is never cached or intercepted.
// The list is checked by tests/test_nitaq_web.py: every shipped file must be here.
const CACHE = "nitaq-0.4.0";
const FILES = [
  "./", "index.html", "app.css", "icon.svg", "manifest.webmanifest", "bundle.js", "engine/worker-bundle.js", "fonts.css",
  "app/main.js", "app/dom.js", "app/i18n.js", "app/check.js", "app/learn.js", "app/computer.js", "app/about.js",
  "engine/data.js", "engine/pyutil.js", "engine/normalizer.js", "engine/scanner.js", "engine/skillscan.js",
  "engine/docs.js", "engine/check.js", "engine/worker.js",
  "fonts/plex-arabic-arabic-400.woff2", "fonts/plex-arabic-arabic-600.woff2", "fonts/plex-arabic-arabic-700.woff2",
  "fonts/plex-arabic-latin-400.woff2", "fonts/plex-arabic-latin-600.woff2", "fonts/plex-arabic-latin-700.woff2",
  "icons/icon-192.png", "icons/icon-512.png", "icons/maskable-512.png",
  "samples/samples.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("nitaq-") && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.includes("/api/")) return;
  e.respondWith(
    fetch(e.request).then((r) => {
      if (r.ok && r.type === "basic") { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.match(e.request, {ignoreSearch: true}).then((m) => m || caches.match("index.html")))
  );
});
