// Single fetch wrapper for the API. The session lives in an HttpOnly cookie set by
// the server; this code never sees or stores tokens.

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }

  /** Optimistic-lock conflict: someone else changed the record. */
  get isConflict(): boolean {
    return this.status === 409
  }
}

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function csrfToken(): string | undefined {
  // Double-submit token (Phase 3): readable cookie, echoed in a header.
  return document.cookie
    .split('; ')
    .find((c) => c.startsWith('mdm_csrf='))
    ?.slice('mdm_csrf='.length)
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (UNSAFE_METHODS.has(method)) {
    const token = csrfToken()
    if (token) headers.set('X-CSRF-Token', token)
  }

  const res = await fetch(path, { ...init, method, headers, credentials: 'same-origin' })
  const body: unknown = res.headers.get('content-type')?.includes('application/json')
    ? await res.json()
    : null

  if (!res.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : res.statusText
    throw new ApiError(res.status, detail, body)
  }
  return body as T
}
