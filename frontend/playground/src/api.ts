export type Health = { status: string; mode: string; mongodb: string; auth: string }
export type User = { id: string; email: string }
export type Token = { access_token: string; expires_in: number }

export class ApiError extends Error {
  readonly status: number
  readonly requestId?: string

  constructor(message: string, status: number, requestId?: string) {
    super(message)
    this.status = status
    this.requestId = requestId
  }
}

export async function request(path: string, options: RequestInit = {}, token?: string) {
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { ...options, headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const retry = response.headers.get('Retry-After')
    const message = payload?.error?.message ?? `Request failed (HTTP ${response.status}).`
    throw new ApiError(retry ? `${message} Retry in ${retry}s.` : message, response.status,
      payload?.error?.request_id ?? response.headers.get('X-Request-ID') ?? undefined)
  }
  return response
}

export async function json<T>(path: string, options?: RequestInit, token?: string): Promise<T> {
  return (await request(path, options, token)).json()
}

export async function health(signal: AbortSignal): Promise<Health> {
  const response = await fetch('/health', { signal })
  const body = await response.json()
  if (typeof body.mode !== 'string') throw new Error('Backend health is unavailable.')
  return body
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} Request ID: ${error.requestId}` : error.message
  }
  return 'Could not complete the request. Check that the backend is running and try again.'
}
