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

/** Fired when the server says the session is gone (expired, logged out elsewhere). */
export const UNAUTHENTICATED_EVENT = 'mdm:unauthenticated'

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const CSRF_COOKIE = '__Host-mdm_csrf'

function csrfToken(): string | undefined {
  // Double-submit token: the server set it as a readable cookie at login.
  const prefix = `${CSRF_COOKIE}=`
  return document.cookie
    .split('; ')
    .find((c) => c.startsWith(prefix))
    ?.slice(prefix.length)
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
  // 204 No Content (and any empty body) is valid even when labelled application/json.
  const raw = await res.text()
  const body: unknown =
    raw !== '' && res.headers.get('content-type')?.includes('application/json')
      ? (JSON.parse(raw) as unknown)
      : null

  if (!res.ok) {
    if (res.status === 401 && path !== '/api/me') {
      window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))
    }
    throw new ApiError(res.status, errorMessage(res, body), body)
  }
  return body as T
}

function errorMessage(res: Response, body: unknown): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const { detail } = body
    if (typeof detail === 'string') return detail
  }
  return res.statusText || `Request failed (${String(res.status)})`
}

/** Human-readable message for any thrown value. */
export function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422 && Array.isArray((error.body as { errors?: unknown }).errors)) {
      const errors = (error.body as { errors: { loc: unknown[]; msg: string }[] }).errors
      return errors.map((e) => `${String(e.loc.at(-1))}: ${e.msg}`).join('; ')
    }
    return error.message
  }
  return error instanceof Error ? error.message : 'Something went wrong'
}

export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
