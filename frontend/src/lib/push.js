// Browser side of Web Push: register the service worker, ask permission, subscribe.
import { api } from './api'

export function swUrl() {
  return import.meta.env.DEV ? '/sw.js?dev=1' : '/sw.js'
}

export async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return null
  try {
    return await navigator.serviceWorker.register(swUrl())
  } catch {
    return null
  }
}

export function pushSupport() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return { supported: false, reason: 'This browser does not support push notifications.' }
  }
  if (!window.isSecureContext) {
    return { supported: false, reason: 'Push needs HTTPS (or http://localhost).' }
  }
  return { supported: true, permission: Notification.permission }
}

function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

export async function currentSubscription() {
  const reg = await navigator.serviceWorker.getRegistration()
  return reg ? reg.pushManager.getSubscription() : null
}

export async function enablePush() {
  const support = pushSupport()
  if (!support.supported) throw new Error(support.reason)
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') throw new Error('Notifications are blocked for this site. Allow them in the browser’s site settings.')
  const reg = (await registerServiceWorker()) || (await navigator.serviceWorker.ready)
  await navigator.serviceWorker.ready
  const { public_key: key } = await api.get('/push/public-key')
  let sub = await reg.pushManager.getSubscription()
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) })
  const json = sub.toJSON()
  return api.post('/push/subscribe', { endpoint: json.endpoint, keys: json.keys })
}

export async function disablePush() {
  const sub = await currentSubscription()
  if (sub) {
    await api.delete('/push/subscribe', null, { endpoint: sub.endpoint }).catch(() => {})
    await sub.unsubscribe()
  }
}
