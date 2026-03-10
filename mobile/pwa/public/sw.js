const CACHE_NAME = 'retailiq-pwa-cache-v1';
const API_CACHE = 'retailiq-api-cache-v1';
const SYNC_QUEUE = 'retailiq-sync-queue';

const URLS_TO_CACHE = [
  '/',
  '/index.html',
  '/manifest.json',
  '/static/js/bundle.js',
  '/static/css/main.css'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(URLS_TO_CACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.filter((name) => name !== CACHE_NAME && name !== API_CACHE)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Network first, falling back to cache strategy for API calls
self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/api/v1/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clonedResponse = response.clone();
          caches.open(API_CACHE).then((cache) => {
            cache.put(event.request, clonedResponse);
          });
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  } else {
    // Cache first, falling back to network for static assets
    event.respondWith(
      caches.match(event.request).then((response) => {
        return response || fetch(event.request);
      })
    );
  }
});

// Background sync for offline mutations
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-transactions') {
    event.waitUntil(syncTransactions());
  }
});

async function syncTransactions() {
  // Logic to process indexedDB queue and push to backend using CRDT
}
