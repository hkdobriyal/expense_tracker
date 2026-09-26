// Thin fetch wrapper for the Ledgerly API.
// - Cookies carry the session (HttpOnly; JavaScript never sees it).
// - Every state-changing request echoes the CSRF token returned at login.

let csrfToken = ''

export function setCsrfToken(token) {
  csrfToken = token || ''
}

export class ApiError extends Error {
  constructor(status, message, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

async function request(method, path, { body, params, form, raw } = {}) {
  const url = new URL(`/api${path}`, window.location.origin)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue
      if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, v))
      else url.searchParams.set(key, value)
    }
  }
  const headers = {}
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let response
  try {
    response = await fetch(url, { method, headers, body: payload, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'Cannot reach the Ledgerly API. Is the backend running on port 8000?')
  }
  if (raw && response.ok) return response
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await response.json() : null
  if (!response.ok) {
    const message = data?.detail || `Request failed (${response.status})`
    throw new ApiError(response.status, typeof message === 'string' ? message : JSON.stringify(message), data)
  }
  return data
}

export const api = {
  get: (path, params) => request('GET', path, { params }),
  post: (path, body, params) => request('POST', path, { body, params }),
  put: (path, body) => request('PUT', path, { body }),
  patch: (path, body) => request('PATCH', path, { body }),
  delete: (path, params) => request('DELETE', path, { params }),
  upload: (path, form, params) => request('POST', path, { form, params }),
  download: async (path, params, fallbackName) => {
    const response = await request('GET', path, { params, raw: true })
    const disposition = response.headers.get('content-disposition') || ''
    const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] || fallbackName
    const blob = await response.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = name
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  },
}
