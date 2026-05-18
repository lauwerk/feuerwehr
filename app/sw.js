const CACHE = "fw-lernapp-v1";
const PRECACHE = [
  "/feuerwehr/",
  "/feuerwehr/index.html",
  "/feuerwehr/cache/manifest.json",
  "/feuerwehr/cache/tags.json",
  "/feuerwehr/cache/topics.json",
  "/feuerwehr/cache/posts.json",
  "/feuerwehr/cache/files_index.json"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  // Cache-first für lokale Assets, Network-first für externe
  const url = new URL(e.request.url);
  if (url.origin === location.origin) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      }))
    );
  }
});
