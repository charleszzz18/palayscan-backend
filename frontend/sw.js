const CACHE_NAME = 'rice-health-cache-v3'; // Unique name for this version of the cache
const urlsToCache = [ // List of local assets that should be available offline
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/manifest.json'
];

self.addEventListener('install', event => { // Triggered when the service worker is first installed
  self.skipWaiting(); // Force active immediately
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  // CRITICAL: Only cache GET requests. Caching POST requests throws "Request method 'POST' is unsupported"
  if (event.request.method !== 'GET') {
    return; // Let browser handle POST/upload directly without interception
  }

  // Do not intercept external backend API calls (e.g., Render, Weather)
  if (!event.request.url.startsWith(self.location.origin)) {
    return; // Direct network request
  }

  // Network-first strategy for local static assets: Try network, fallback to cache if offline
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (!response || response.status !== 200 || response.type !== 'basic') {
          return response;
        }
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          cache.put(event.request, responseClone);
        });
        return response;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Clearing old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});
