const CACHE_NAME = 'fleetpulse-v1.0.2';
const OFFLINE_URL = '/offline.html';

// Assets to cache immediately
const STATIC_ASSETS = [
  '/offline.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

// Install event - cache essential assets
self.addEventListener('install', (event) => {
  console.log('FleetPulse SW: Installing...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('FleetPulse SW: Caching essential assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('FleetPulse SW: Installation complete');
        // Force the waiting service worker to become the active service worker
        return self.skipWaiting();
      })
  );
});

// Allow the app to activate a freshly installed worker immediately.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('FleetPulse SW: Activating...');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('FleetPulse SW: Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('FleetPulse SW: Now ready to handle fetches');
      // Ensure the new service worker takes control immediately
      return self.clients.claim();
    })
  );
});

// Fetch event - implement caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // API calls must stay live; do not serve stale telemetry or AI config.
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // Static assets - Cache First strategy
  if (
    request.destination === 'script' ||
    request.destination === 'style' ||
    request.destination === 'image' ||
    request.destination === 'font' ||
    request.destination === 'manifest' ||
    url.pathname.includes('.js') ||
    url.pathname.includes('.css') ||
    url.pathname.includes('.png') ||
    url.pathname.includes('.jpg') ||
    url.pathname.includes('.svg') ||
    url.pathname.includes('.woff') ||
    url.pathname.includes('.woff2')
  ) {
    event.respondWith(
      caches.match(request)
        .then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          
          return fetch(request).then((response) => {
            // Cache the new resource
            if (response.status === 200) {
              const responseClone = response.clone();
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(request, responseClone);
              });
            }
            
            return response;
          });
        })
    );
    return;
  }

  // HTML pages - Network First with offline fallback
  if (request.destination === 'document') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          return response;
        })
        .catch(() => {
          return caches.match(OFFLINE_URL);
        })
    );
    return;
  }
});

// Background sync for when connection is restored
self.addEventListener('sync', (event) => {
  if (event.tag === 'background-sync') {
    console.log('FleetPulse SW: Background sync triggered');
    // Handle background sync logic here
  }
});

// Push notifications support (future enhancement)
self.addEventListener('push', (event) => {
  if (event.data) {
    const data = event.data.json();
    console.log('FleetPulse SW: Push received:', data);
    
    const options = {
      body: data.body,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      vibrate: [100, 50, 100],
      data: data.data
    };

    event.waitUntil(
      self.registration.showNotification(data.title, options)
    );
  }
});
