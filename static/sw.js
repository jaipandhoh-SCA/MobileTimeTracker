/*  Service Worker — offline-tolerant shell + sync queue.
 *
 *  Strategy:
 *  - App shell (HTML, CSS, JS) → Cache-first with network fallback
 *  - API/data requests → Network-first with cache fallback
 *  - POST/PUT/DELETE while offline → queued in IndexedDB, replayed on reconnect
 */

const CACHE_NAME = 'adu-shell-v1';

const SHELL_URLS = [
  '/home',
  '/static/favicon.jpg',
  '/static/manifest.json',
];

/* ── Install: cache app shell ── */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS))
  );
  self.skipWaiting();
});

/* ── Activate: clean old caches ── */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

/* ── Fetch: network-first for data, cache-first for shell ── */
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Skip non-GET requests (we queue mutations via background sync)
  if (request.method !== 'GET') return;

  // API routes → network-first
  if (request.url.includes('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // CDN assets → cache-first
  if (request.url.includes('cdn.')) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((resp) => {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then((c) => c.put(request, clone));
        return resp;
      }))
    );
    return;
  }

  // Everything else → network-first, fall back to cache, then offline page
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match(request).then((cached) =>
          cached || new Response(
            '<html><body style="font-family:system-ui;padding:2rem;text-align:center">'
            + '<h1>Offline</h1><p>You are offline. Queued actions will sync when reconnected.</p>'
            + '</body></html>',
            { headers: { 'Content-Type': 'text/html' } }
          )
        )
      )
  );
});

/* ── Background Sync — replay queued mutations ── */
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-queue') {
    event.waitUntil(replayQueue());
  }
});

async function replayQueue() {
  const db = await openSyncDB();
  const tx = db.transaction('queue', 'readonly');
  const store = tx.objectStore('queue');
  const items = await getAllFromStore(store);

  for (const item of items) {
    try {
      await fetch(item.url, {
        method: item.method,
        headers: item.headers,
        body: item.body,
      });
      // Remove from queue on success
      const delTx = db.transaction('queue', 'readwrite');
      delTx.objectStore('queue').delete(item.id);
    } catch (e) {
      // Leave in queue for next sync attempt
      break;
    }
  }
}

function openSyncDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('adu-sync', 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function getAllFromStore(store) {
  return new Promise((resolve, reject) => {
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
