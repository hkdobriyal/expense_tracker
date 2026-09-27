// Hisaab service worker: Web Push notifications + offline app shell (production only).
// Registered as /sw.js in production and /sw.js?dev=1 in development (push only, no caching).
const DEV = new URL(self.location.href).searchParams.has('dev')
const CACHE_NAME = 'hisaab-shell-v1'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon.svg', '/icon-192.png', '/icon-512.png', '/favicon.ico']

self.addEventListener('install', (event) => {
  if (DEV) { self.skipWaiting(); return }
  event.waitUntil(caches.open(CACHE_NAME).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME || DEV).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  if (DEV) return
  const request = event.request
  const url = new URL(request.url)
  // Never cache API calls, the live event stream, or anything cross-origin.
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api')) return
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/index.html')))
    return
  }
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request).then((response) => {
        if (response.ok && response.type === 'basic') {
          const copy = response.clone()
          caches.open(CACHE_NAME).then((c) => c.put(request, copy))
        }
        return response
      }).catch(() => cached)
      return cached || network
    }),
  )
})

// --- Push -------------------------------------------------------------------------------------
self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data ? event.data.json() : {} } catch { data = { title: 'Hisaab', body: event.data?.text() } }
  const title = data.title || 'Hisaab'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: '/icon-192.png',
      badge: '/badge-96.png',
      tag: data.tag || title,
      renotify: false,
      data: { url: data.url || '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = new URL(event.notification.data?.url || '/', self.location.origin).href
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => w.url.startsWith(self.location.origin))
      if (open) { open.focus(); return open.navigate(target) }
      return self.clients.openWindow(target)
    }),
  )
})
