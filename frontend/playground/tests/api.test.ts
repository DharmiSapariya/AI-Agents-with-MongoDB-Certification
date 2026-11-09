import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiError, health, request } from '../src/api.ts'

test('request sends a bearer token and preserves structured errors and retry metadata', async t => {
  t.mock.method(globalThis, 'fetch', async (_: string, init: RequestInit) => {
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer test-token')
    return new Response(JSON.stringify({ error: { message: 'Slow down', request_id: 'req-1' } }),
      { status: 429, headers: { 'Retry-After': '3' } })
  })
  await assert.rejects(request('/api/chat', { method: 'POST', body: '{}' }, 'test-token'), error =>
    error instanceof ApiError && error.status === 429 && error.requestId === 'req-1' &&
    error.message === 'Slow down Retry in 3s.')
})

test('health shows the backend mode even when readiness returns 503', async t => {
  const status = { status: 'degraded', mode: 'live', mongodb: 'unreachable', auth: 'enabled' }
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify(status), { status: 503 }))
  assert.deepEqual(await health(new AbortController().signal), status)
})
