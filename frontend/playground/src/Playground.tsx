import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, errorText, json, request } from './api'
import { readEvents, type Citation, type Result, type Trace } from './stream'

type Session = { id: string; updated_at: string; turns: number }
type Turn = { execution_id: string; question: string | null; answer: string | null; citations: Citation[];
  status: string; outcome: string | null }

function sourceLink(source: string | null) {
  if (!source) return null
  try {
    const url = new URL(source)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

function Citations({ items }: { items: Citation[] }) {
  if (!items.length) return null
  return <details className="citations">
    <summary>Evidence · {items.length} {items.length === 1 ? 'source' : 'sources'}</summary>
    <ul>{items.map(item => {
      const link = sourceLink(item.source)
      return <li key={item.id}><strong>{item.title}</strong>
        <small>{item.collection} / {item.document_id}{item.chunk_index != null && ` / chunk ${item.chunk_index}`}</small>
        {link ? <a href={link} target="_blank" rel="noreferrer">Open source</a> : item.source && <small>{item.source}</small>}
      </li>
    })}</ul>
  </details>
}

export function Playground({ token, email, onExpired, onInspect }: { token: string; email: string; onExpired: () => void;
  onInspect: (id: string) => void }) {
  const [sessions, setSessions] = useState<Session[]>()
  const [selected, setSelected] = useState<string>()
  const [history, setHistory] = useState<Turn[]>()
  const [revision, setRevision] = useState(0)
  const [message, setMessage] = useState('')
  const [sessionFilter, setSessionFilter] = useState('')
  const [showInspector, setShowInspector] = useState(true)
  const [copyStatus, setCopyStatus] = useState('')
  const [memory, setMemory] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [trace, setTrace] = useState<Trace[]>([])
  const [result, setResult] = useState<Result>()
  const [error, setError] = useState('')
  const [listError, setListError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [activity, setActivity] = useState('')
  const [busy, setBusy] = useState(false)
  const active = useRef<AbortController | null>(null)

  useEffect(() => () => active.current?.abort(), [])
  useEffect(() => {
    const controller = new AbortController()
    json<Session[]>('/api/sessions?limit=50', { signal: controller.signal }, token).then(rows => {
      if (!controller.signal.aborted) { setSessions(rows); setListError('') }
    }).catch(failure => {
      if (controller.signal.aborted) return
      if (failure instanceof ApiError && failure.status === 401) onExpired()
      else setListError(errorText(failure))
    })
    return () => controller.abort()
  }, [token, revision, onExpired])

  useEffect(() => {
    if (!selected) return
    const controller = new AbortController()
    json<Turn[]>(`/api/sessions/${encodeURIComponent(selected)}/history?limit=50`,
      { signal: controller.signal }, token).then(turns => {
      if (!controller.signal.aborted) { setHistory(turns); setHistoryError('') }
    }).catch(failure => {
      if (controller.signal.aborted) return
      if (failure instanceof ApiError && failure.status === 401) onExpired()
      else setHistoryError(errorText(failure))
    })
    return () => controller.abort()
  }, [token, selected, revision, onExpired])

  function select(id?: string) {
    if (id === selected) return
    setSelected(id)
    setHistory(undefined)
    setHistoryError('')
    setResult(undefined)
    setPrompt('')
    setTrace([])
    setError('')
    setActivity('')
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const question = message.trim()
    if (!question || active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    setResult(undefined)
    setTrace([])
    setPrompt(question)
    setMessage('')
    setActivity('Opening execution stream…')
    try {
      const response = await request('/api/chat/stream', {
        method: 'POST', signal: controller.signal,
        body: JSON.stringify({ message: question, session_id: selected, use_memory: memory }),
      }, token)
      if (!response.body) throw new Error('Missing stream')
      for await (const frame of readEvents(response.body)) {
        if (frame.event === 'session') {
          setSelected(frame.data.session_id)
          setActivity('Agent is running…')
        } else if (frame.event === 'trace') {
          const item = frame.data
          setTrace(previous => [...previous.slice(-49), item])
        } else if (frame.event === 'result') {
          setResult(frame.data)
          setActivity('Run finished.')
          return
        } else {
          setError(`${frame.data.error.message} Request ID: ${frame.data.error.request_id}`)
          setActivity('')
          return
        }
      }
      setActivity('')
      setError('The stream ended before a result arrived. Refresh history before sending the question again.')
    } catch (failure) {
      if (controller.signal.aborted) setActivity('Stream stopped. The server may still finish the turn.')
      else if (failure instanceof ApiError && failure.status === 401) onExpired()
      else { setError(errorText(failure)); setActivity('') }
    } finally {
      active.current = null
      setBusy(false)
      setRevision(value => value + 1)
    }
  }

  const filteredSessions = sessions?.filter(session => session.id.toLowerCase().includes(sessionFilter.trim().toLowerCase()))
  async function copyAnswer(answer: string) {
    try {
      await navigator.clipboard.writeText(answer)
      setCopyStatus('Answer copied.')
    } catch {
      setCopyStatus('Clipboard unavailable. You can still select and copy the answer.')
    }
  }

  const recent = history ? [...history].reverse() : []
  const alreadyRecorded = result && recent.some(turn => turn.execution_id === result.execution_id)

  return <div className={`workspace chat-layout ${showInspector ? "with-inspector" : ""}`}>
    <aside className="card sessions" aria-labelledby="sessions-heading">
      <p className="eyebrow">YOUR WORKSPACE</p>
      <h2 id="sessions-heading">Sessions</h2>
      <p className="muted wrap">{email}</p>
      <button className="quiet" disabled={busy || !selected} onClick={() => select()}>New chat</button>
      {sessions && sessions.length > 0 && <label className="session-search">Find by session ID
        <input type="search" value={sessionFilter} onChange={event => setSessionFilter(event.target.value)} />
      </label>}
      {listError ? <p className="error" role="alert">{listError}</p> : !sessions ? <p>Loading sessions…</p>
        : !sessions.length ? <p className="muted">No sessions yet.</p>
        : !filteredSessions?.length ? <p className="muted">No matching sessions.</p>
        : <ul className="session-list">{filteredSessions.map(session =>
          <li key={session.id}><button className="quiet" disabled={busy}
            aria-pressed={selected === session.id} onClick={() => select(session.id)}>
            <span>{session.id.slice(0, 10)}</span><small>{session.turns} turns</small>
          </button></li>)}</ul>}
    </aside>
    <section className="card conversation" aria-labelledby="conversation-heading">
      <div className="section-heading">
        <h2 id="conversation-heading">{selected ? 'Conversation' : 'New conversation'}</h2>
        <div className="button-row">
          <button className="quiet" disabled={busy} onClick={() => setRevision(value => value + 1)}>Refresh history</button>
          <button className="quiet" aria-expanded={showInspector} aria-controls="run-inspector"
            onClick={() => setShowInspector(value => !value)}>{showInspector ? 'Hide inspector' : 'Show inspector'}</button>
        </div>
      </div>
      {historyError && <p className="error" role="alert">{historyError}</p>}
      {selected && !history && !historyError && <p className="muted">Loading history…</p>}
      {!selected && !prompt && <div className="prompt-starters">
        <p className="eyebrow">START WITH A QUESTION</p>
        {['Can I query the first field of a compound index by itself?', 'Explain how MongoDB change streams resume.',
          'How do I group documents in an aggregation pipeline?'].map(example =>
          <button key={example} className="quiet" onClick={() => setMessage(example)}>{example}</button>)}
      </div>}
      {recent.map(turn => <article className="turn" key={turn.execution_id}>
        <p className="question">{turn.question ?? 'Question unavailable in trace'}</p>
        <p>{turn.answer ?? 'This run ended without a recorded answer.'}</p>
        <Citations items={turn.citations} />
        <div className="button-row">
          <button className="quiet" onClick={() => onInspect(turn.execution_id)}>Replay run</button>
          {turn.answer && <button className="quiet" onClick={() => void copyAnswer(turn.answer ?? "")}>Copy answer</button>}
        </div>
      </article>)}
      {!alreadyRecorded && prompt && <article className="turn">
        <p className="question">{prompt}</p>
        {result && <><p>{result.answer}</p><Citations items={result.citations} /></>}
      </article>}
      {copyStatus && <p className="muted" role="status">{copyStatus}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {activity && <p className="muted" role="status">{activity}</p>}
      <form className="composer" onSubmit={send}>
        <label>Ask about MongoDB<textarea value={message} onChange={event => setMessage(event.target.value)}
          required maxLength={2000} rows={3} placeholder="How do compound index prefixes work?" /></label>
        <div className="composer-actions">
          <label className="checkbox"><input type="checkbox" checked={memory}
            onChange={event => setMemory(event.target.checked)} /> Use my saved notes</label>
          {busy ? <button type="button" className="quiet" onClick={() => active.current?.abort()}>Stop stream</button>
            : <button className="primary" disabled={!message.trim()} type="submit">Send question</button>}
        </div>
      </form>
    </section>
    <aside className="card inspector" id="run-inspector" hidden={!showInspector} aria-labelledby="inspector-title">
      <p className="eyebrow">RUN METADATA</p><h2 id="inspector-title">Execution inspector</h2>
      {!trace.length && !result && <p className="muted">Send a question to follow its recorded events.</p>}
      {trace.length > 0 && <ol className="inspector-events">{trace.map(item =>
        <li key={item.seq}><span>{item.seq}</span><div>{item.type}<small>{item.node}</small></div></li>)}</ol>}
      {result && <>
        <p className="muted wrap">Run {result.execution_id} · {result.outcome.replaceAll('_', ' ')}
          {!result.fully_recorded && ' · trace incomplete'}</p>
        <Citations items={result.citations} />
        {!alreadyRecorded && <div className="button-row">
          <button className="quiet" onClick={() => onInspect(result.execution_id)}>Replay run</button>
          <button className="quiet" onClick={() => void copyAnswer(result.answer)}>Copy answer</button>
        </div>}
      </>}
    </aside>
  </div>
}
