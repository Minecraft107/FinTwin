// Thin fetch wrapper: unwraps the backend {data, meta} envelope and turns
// {error: {code, message, details}} responses into ApiError.
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export async function request(path, { method = 'GET', body, headers = {} } = {}) {
  const isForm = body instanceof FormData
  let res
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body && !isForm ? { 'Content-Type': 'application/json', ...headers } : headers,
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
    throw new ApiError(res.status, err.code ?? 'HTTP_ERROR', err.message ?? res.statusText, err.details)
  }
  return payload
}
