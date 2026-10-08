// Thin fetch wrapper: adds the JWT, unwraps the backend {data, meta} envelope and turns
// {error: {code, message, details}} responses into ApiError.
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'
const TOKEN_KEY = 'fintwin.token'

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set: (token) => {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token)
      else localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* storage unavailable: the session lasts until reload */
    }
  },
}

export async function request(path, { method = 'GET', body, headers = {} } = {}) {
  const isForm = body instanceof FormData
  const token = tokenStore.get()
  let res
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: {
        ...(body && !isForm ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body && !isForm ? JSON.stringify(body) : body,
    })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the FinTwin server.')
  }

  if (res.status === 204) return { data: null, meta: {} }
  const payload = await res.json().catch(() => null)
  // /health answers 503 *with* data when degraded; every other error has no data.
  if (!res.ok && !payload?.data) {
    const err = payload?.error ?? {}
    if (res.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('fintwin:logout'))
    }
    throw new ApiError(res.status, err.code ?? 'HTTP_ERROR', err.message ?? res.statusText, err.details)
  }
  return payload
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  del: (path) => request(path, { method: 'DELETE' }),
}

// Pydantic validation details -> one readable line.
export function errorText(error) {
  if (!error) return ''
  if (Array.isArray(error.details) && error.details.length) {
    return error.details
      .map((d) => `${(d.loc ?? []).filter((x) => x !== 'body').join('.') || 'value'}: ${d.msg}`)
      .join('; ')
  }
  return error.message
}
