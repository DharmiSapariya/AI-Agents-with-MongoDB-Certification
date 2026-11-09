export type Citation = { id: string; title: string; collection: string; document_id: string;
  source: string | null; chunk_index: number | null }
export type Trace = { execution_id: string; request_id: string; seq: number; type: string; node: string | null }
export type Result = { answer: string; outcome: string; citations: Citation[]; execution_id: string;
  session_id: string; request_id: string; fully_recorded: boolean }
export type StreamEvent =
  | { event: 'session'; data: { session_id: string; request_id: string } }
  | { event: 'trace'; data: Trace }
  | { event: 'result'; data: Result }
  | { event: 'failed'; data: { error: { message: string; request_id: string } } }

export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      buffer += decoder.decode(value, { stream: true })
      let separator = /\r?\n\r?\n/.exec(buffer)
      while (separator) {
        const frame = buffer.slice(0, separator.index)
        buffer = buffer.slice(separator.index + separator[0].length)
        const lines = frame.split(/\r?\n/)
        const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim()
        const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
        if (data && (event === 'session' || event === 'trace' || event === 'result' || event === 'failed')) {
          yield { event, data: JSON.parse(data) }
        }
        separator = /\r?\n\r?\n/.exec(buffer)
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
