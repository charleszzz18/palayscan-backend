const CACHE_NAME = 'rice-health-cache-v2'; // Unique name for this version of the cache
const urlsToCache = [ // List of local assets that should be available offline
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/manifest.json'
];

self.addEventListener('install', event => { // Triggered when the service worker is first installed
  event.waitUntil( // Ensures the installation doesn't finish until the cache is populated
    caches.open(CACHE_NAME) // Create or open the specific cache container
      .then(cache => {
        console.log('Opened cache'); // Log status for debugging
        return cache.addAll(urlsToCache); // Download and store all listed files
      })
  );
});

self.addEventListener('fetch', event => { // Intercepts every network request made by the app
  // Network-first strategy: Always try to get fresh data, fallback to cache if offline
  event.respondWith(
    fetch(event.request) // Attempt to fetch the resource from the live server
      .then(response => {
        // If network succeeds, update the cache and return the network response
        const responseClone = response.clone(); // Clone the response because it can only be consumed once
        caches.open(CACHE_NAME).then(cache => {
          cache.put(event.request, responseClone); // Save the fresh copy in the cache
        });
        return response; // Deliver the live response to the browser
      })
      .catch(() => { // Triggered if the network is unavailable (e.g. no signal in the rice field)
        // If network fails (offline), return the version stored in the cache
        return caches.match(event.request);
      })
  );
});

self.addEventListener('activate', event => { // Triggered when a new version of the service worker takes control
  const cacheWhitelist = [CACHE_NAME]; // List of caches we want to keep
  event.waitUntil(
    caches.keys().then(cacheNames => { // Get all existing cache containers
      return Promise.all(
        cacheNames.map(cacheName => { // Loop through all caches found on the device
          if (cacheWhitelist.indexOf(cacheName) === -1) { // If the cache is not in our whitelist
            return caches.delete(cacheName); // Delete the old, outdated cache
          }
        })
      );
    })
  );
});
