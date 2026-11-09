import { useEffect, useState } from 'react'
import { type Access, useResource } from './resources'

type Event = {
  execution_id: string; seq: number; type: string; node: string | null; ts: string
  data: { [key: string]: unknown; status?: string; outcome?: string; duration_ms?: number; fully_recorded?: boolean; tool?: string }
}
const PAGE_SIZE = 10

function Timeline({ events }: { events: Event[] }) {
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(false)
  const last = events.length - 1
  const index = Math.min(cursor, last)
  useEffect(() => {
    if (!playing || index >= last) return
    const timer = window.setTimeout(() => {
      setCursor(index + 1)
      if (index + 1 === last) setPlaying(false)
    }, 700)
    return () => window.clearTimeout(timer)
  }, [playing, index, last])
  const event = events[index]
  const incomplete = events[last].type !== 'execution_end' || events[last].data.fully_recorded === false ||
    events.some((entry, position) => entry.seq !== position + 1)
  return <>
    {incomplete && <p className="notice" role="status">Some execution events may be missing.</p>}
    <div className="button-row" aria-label="Playback controls">
      <button className="quiet" onClick={() => { setPlaying(false); setCursor(0) }}>Restart</button>
      <button className="quiet" disabled={index <= 0} onClick={() => { setPlaying(false); setCursor(index - 1) }}>Previous</button>
      <button className="quiet" disabled={index >= last} onClick={() => setPlaying(!playing)}>{playing ? 'Pause' : 'Play'}</button>
      <button className="quiet" disabled={index >= last} onClick={() => { setPlaying(false); setCursor(index + 1) }}>Next</button>
    </div>
    <div className="replay-progress"><p role="status">Event {index + 1} of {events.length}</p>
      <progress aria-label="Playback progress" value={index + 1} max={events.length} />
    </div>
    <dl className="event-detail">
      <dt>Event</dt><dd>{event.type}</dd>
      <dt>Node</dt><dd>{event.node ?? 'Unavailable'}</dd>
      <dt>Recorded</dt><dd>{new Date(event.ts).toLocaleString()}</dd>
      <dt>Status</dt><dd>{event.data.status ?? event.data.outcome ?? 'Unavailable'}</dd>
      {event.data.tool && <><dt>Tool</dt><dd>{event.data.tool}</dd></>}
      {event.data.duration_ms != null && <><dt>Duration</dt><dd>{event.data.duration_ms} ms</dd></>}
    </dl>
    <details className="citations" key={event.seq}>
      <summary>Recorded event data</summary>
      {Object.keys(event.data).length ? <pre className="record">{JSON.stringify(event.data, null, 2)}</pre>
        : <p className="muted">No additional data was recorded.</p>}
    </details>
    <ol className="session-list timeline-list">{events.map((item, i) => <li key={item.seq}>
      <button className="quiet" aria-current={i === index ? 'step' : undefined}
        onClick={() => { setPlaying(false); setCursor(i) }}>
        <span>{item.seq}. {item.type}</span><small>{item.node}</small>
      </button>
    </li>)}</ol>
  </>
}

export function ExecutionReplay({ selected, onSelect, onMentor, ...access }: Access & {
  selected?: string; onSelect: (id: string) => void; onMentor: (id: string) => void
}) {
  const [skip, setSkip] = useState(0)
  const [query, setQuery] = useState('')
  const [outcome, setOutcome] = useState('all')
  const runs = useResource<Event[]>(`/api/executions?limit=${PAGE_SIZE + 1}&skip=${skip}`, access)
  const trace = useResource<Event[]>(selected ? `/api/executions/${encodeURIComponent(selected)}` : null, access)
  const page = runs.data?.slice(0, PAGE_SIZE) ?? []
  const statusOf = (run: Event) => run.data.outcome ?? run.data.status ?? 'Recorded'
  const options = [...new Set(page.map(statusOf))]
  const filtered = page.filter(run => run.execution_id.toLowerCase().includes(query.trim().toLowerCase()) &&
    (outcome === 'all' || outcome === statusOf(run)))
  return <div className="workspace observability-layout">
    <section className="card">
      <h2>Recorded runs</h2>
      <div className="panel-filters">
        <label>Run ID<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <label>Outcome<select value={outcome} onChange={event => setOutcome(event.target.value)}>
          <option value="all">All outcomes</option>
          {options.map(option => <option value={option} key={option}>{option.replaceAll('_', ' ')}</option>)}
        </select></label>
      </div>
      <p className="muted">Filters apply to this page.</p>
      {runs.error ? <p className="error" role="alert">{runs.error}</p> : !runs.data ? <p>Loading runs…</p>
        : runs.data.length === 0 ? <p className="muted">No runs on this page.</p>
        : !filtered.length ? <p className="muted">No matching runs on this page.</p>
        : <ul className="session-list">{filtered.map(run => <li key={run.execution_id}>
          <button className="quiet" aria-pressed={selected === run.execution_id} onClick={() => onSelect(run.execution_id)}>
            <span>{run.execution_id.slice(0, 10)}<small>{new Date(run.ts).toLocaleString()}</small></span><small>{statusOf(run)}</small>
          </button>
        </li>)}</ul>}
      <div className="button-row">
        <button className="quiet" disabled={skip === 0} onClick={() => { setSkip(skip - PAGE_SIZE); setOutcome('all') }}>Previous page</button>
        <button className="quiet" disabled={(runs.data?.length ?? 0) <= PAGE_SIZE || skip >= 1000}
          onClick={() => { setSkip(skip + PAGE_SIZE); setOutcome('all') }}>Next page</button>
        <button className="quiet" onClick={runs.reload}>Refresh</button>
      </div>
    </section>
    <section className="card">
      <div className="section-heading"><h2>Execution timeline</h2>
        {selected && Boolean(trace.data?.length) && <button className="quiet" onClick={() => onMentor(selected)}>Open in Mentor</button>}
      </div>
      {!selected ? <p className="muted">Select a saved run to inspect its events.</p>
        : trace.error ? <p className="error" role="alert">{trace.error}</p>
        : !trace.data ? <p>Loading execution…</p>
        : !trace.data.length ? <p className="muted">No events were returned.</p>
        : <Timeline key={selected} events={trace.data} />}
    </section>
  </div>
}
