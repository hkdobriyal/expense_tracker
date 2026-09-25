const CACHE_NAME = 'ledgerly-cache-v4'
const PRECACHE_ASSETS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/icon.svg',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png'
]

// 1. Install & pre-cache critical shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  )
})

// 2. Activate & prune stale caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  )
})

// 3. Fetch interceptor: Smart separation between App Shell, Static Assets, and Dynamic APIs
self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)

  // Never cache or hijack backend API calls, WebSockets, or Vite dev server internals
  const isApi = url.port === '8000' ||
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/transactions') ||
    url.pathname.startsWith('/accounts') ||
    url.pathname.startsWith('/budgets') ||
    url.pathname.startsWith('/goals') ||
    url.pathname.startsWith('/bills') ||
    url.pathname.startsWith('/dashboard') ||
    url.pathname.startsWith('/analytics') ||
    url.pathname.startsWith('/sync') ||
    url.pathname.startsWith('/backup')

  if (isApi || url.protocol.startsWith('chrome-extension') || url.pathname.includes('/@vite') || url.pathname.includes('/@react-refresh')) {
    return
  }

  // Navigation requests: HTML document navigation -> Network first with /index.html cache fallback
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(async () => {
        const cached = await caches.match('/index.html')
        return cached || new Response('Offline - Ledgerly App Shell', { headers: { 'Content-Type': 'text/html' } })
      })
    )
    return
  }

  // Static assets (CSS, JS, SVG, PNG, fonts): Stale-while-revalidate strategy
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      const fetchPromise = fetch(request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type !== 'opaque') {
          const responseClone = networkResponse.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone))
        }
        return networkResponse
      }).catch(() => {
        // Network failed; cachedResponse will be returned if available
      })

      return cachedResponse || fetchPromise
    })
  )
})
