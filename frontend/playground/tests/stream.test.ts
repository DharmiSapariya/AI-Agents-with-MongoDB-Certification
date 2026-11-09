import assert from 'node:assert/strict'
import test from 'node:test'
import { readEvents } from '../src/stream.ts'

test('reads split UTF-8, CRLF delimiters, and multiple frames in order', async () => {
  const wire = new TextEncoder().encode(
    'event: session\r\ndata: {"session_id":"s1"}\r\n\r\n: heartbeat\n\n' +
    'event: result\ndata: {"answer":"café"}\n\n')
  const input = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const byte of wire) controller.enqueue(Uint8Array.of(byte))
      controller.close()
    },
  })
  const events = []
  for await (const event of readEvents(input)) events.push(event)
  assert.deepEqual(events, [
    { event: 'session', data: { session_id: 's1' } },
    { event: 'result', data: { answer: 'café' } },
  ])
})

test('leaving the stream cancels its reader', async () => {
  let canceled = false
  const input = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('event: failed\ndata: {"error":{"message":"failure"}}\n\n'))
    },
    cancel() { canceled = true },
  })
  for await (const event of readEvents(input)) {
    assert.equal(event.event, 'failed')
    break
  }
  assert.equal(canceled, true)
  assert.equal(input.locked, false)
})
