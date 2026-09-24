// SMART-TECH PWA Service Worker (Phase 10 - Expérience Mobile & Mode Hors-Ligne)
const CACHE_NAME = 'smart-tech-v10';
const OFFLINE_URL = '/offline/';

const PRECACHE_ASSETS = [
  '/',
  '/dashboard/',
  '/dashboard/caisse/',
  '/offline/',
  '/manifest.json',
  '/static/stockapp/css/theme.css',
  '/static/stockapp/js/ui.js',
  '/static/stockapp/images/icon-192.jpg',
  '/static/stockapp/images/icon-512.jpg'
];

// 1. Installation du Service Worker & Pré-mise en cache
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SMART-TECH SW] Mise en cache des ressources critiques PWA');
      return cache.addAll(PRECACHE_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// 2. Activation & Purge des anciens caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[SMART-TECH SW] Nettoyage ancien cache :', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => {
      console.log('[SMART-TECH SW] Service Worker activé et opérationnel');
      return self.clients.claim();
    })
  );
});

// 3. Stratégie de capture réseau & mode hors-ligne
self.addEventListener('fetch', (event) => {
  // Ignorer les requêtes non-GET (POST, PUT, DELETE...)
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // Ignorer les appels admin Django ou endpoints API sensibles qui nécessitent une réponse live
  if (url.pathname.startsWith('/admin/')) return;

  const isHtmlNavigation = event.request.mode === 'navigate' ||
    (event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html'));

  if (isHtmlNavigation) {
    // Stratégie "Network First" pour les pages de navigation
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return networkResponse;
        })
        .catch(async () => {
          // Si le réseau échoue, chercher dans le cache
          const cachedResponse = await caches.match(event.request);
          if (cachedResponse) return cachedResponse;

          // En dernier recours, afficher la page de secours hors-ligne
          return caches.match(OFFLINE_URL);
        })
    );
    return;
  }

  // Stratégie "Cache First with Network Fallback" pour les assets statiques (CSS, JS, Fonts, Images)
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) return cachedResponse;

      return fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      }).catch(() => {
        // En cas d'erreur sur une image hors-ligne, on ne bloque pas
        return null;
      });
    })
  );
});
