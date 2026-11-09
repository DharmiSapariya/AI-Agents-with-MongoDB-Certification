import { useState } from 'react'
import { type Access, useResource } from './resources'

const stages = [
  { id: '01', label: 'Question', title: 'Start an owned conversation',
    detail: 'FastAPI checks the request budget and account before the primary graph starts.' },
  { id: '02', label: 'Retrieval', title: 'Retrieve source evidence',
    detail: 'The primary graph can search indexed chunks or fetch a complete document by title.' },
  { id: '03', label: 'Replay', title: 'Inspect the recorded run',
    detail: 'Saved events show tool calls and outcomes. The independent Mentor explains their recorded metadata.' },
]

export function PlatformHome({ onOpen, onResources }: { onOpen: () => void; onResources: () => void }) {
  const [active, setActive] = useState(0)
  const stage = stages[active]
  return <div className="platform-home">
    <section className="platform-hero" aria-labelledby="platform-heading">
      <div>
        <p className="eyebrow">ENGINEERING WORKSPACE / MONGODB + LANGGRAPH</p>
        <h1 id="platform-heading">Follow an agent<br />from question to <em>evidence.</em></h1>
        <p className="intro">Ask MongoDB questions, inspect the retrieved sources, and replay the recorded execution with a separate Mentor.</p>
        <div className="button-row">
          <button className="primary" onClick={onOpen}>Open workspace <span aria-hidden="true">↗</span></button>
          <button className="quiet" onClick={onResources}>Explore project resources</button>
        </div>
      </div>
      <section className="flow-panel" aria-labelledby="flow-heading">
        <div className="flow-header"><h2 id="flow-heading">How a run works</h2><span>ARCHITECTURE GUIDE</span></div>
        <div className="flow-stages" aria-label="Execution stages">
          {stages.map((item, index) => <button key={item.id} className="quiet" aria-pressed={active === index}
            onClick={() => setActive(index)}><small>{item.id}</small>{item.label}</button>)}
        </div>
        <div className="flow-description" aria-live="polite">
          <p className="eyebrow">STAGE {stage.id}</p><h3>{stage.title}</h3><p>{stage.detail}</p>
        </div>
        <p className="flow-footer">Conceptual overview. Open a saved run to see its recorded events.</p>
      </section>
    </section>
    <section className="platform-features" aria-label="Platform capabilities">
      <article><span>01 / BUILD</span><h2>Primary agent</h2><p>Ask a question and follow tool execution as it happens.</p></article>
      <article><span>02 / OBSERVE</span><h2>Execution replay</h2><p>Inspect saved events, citation metadata, and operational metrics.</p></article>
      <article><span>03 / LEARN</span><h2>Independent Mentor</h2><p>Walk through a recorded trace or practice with quizzes and challenges.</p></article>
    </section>
  </div>
}

type Summary = {
  executions: { completed: number; errors: number; mean_duration_ms: number | null }
  usage: { total_tokens: number | null }
}
type Run = { execution_id: string; ts: string; data: { outcome?: string; status?: string } }

export function PlatformDashboard({ onOpen, onReplay, ...access }: Access & {
  onOpen: () => void; onReplay: (id: string) => void
}) {
  const summary = useResource<Summary>('/api/analytics/summary?days=7', access)
  const runs = useResource<Run[]>('/api/executions?limit=5', access)
  const data = summary.data
  return <div className="dashboard-grid">
    <section className="card">
      <div className="section-heading"><h2>Last 7 days</h2>
        <button className="quiet" onClick={() => { summary.reload(); runs.reload() }}>Refresh activity</button></div>
      {summary.error ? <p className="error" role="alert">{summary.error}</p> : !data ? <p>Loading activity…</p> :
        <dl className="metric-grid">
          <div><dt>Finished runs</dt><dd>{data.executions.completed}</dd></div>
          <div><dt>Execution errors</dt><dd>{data.executions.errors}</dd></div>
          <div><dt>Mean duration</dt><dd>{data.executions.mean_duration_ms == null ? 'Unavailable' : `${Math.round(data.executions.mean_duration_ms)} ms`}</dd></div>
          <div><dt>Reported tokens</dt><dd>{data.usage.total_tokens?.toLocaleString() ?? 'Unavailable'}</dd></div>
        </dl>}
      <button className="primary" onClick={onOpen}>Ask a question</button>
    </section>
    <section className="card">
      <h2>Recent recorded runs</h2>
      {runs.error ? <p className="error" role="alert">{runs.error}</p> : !runs.data ? <p>Loading runs…</p> :
        !runs.data.length ? <p className="muted">Your finished runs will appear here.</p> :
          <ul className="session-list">{runs.data.map(run => <li key={run.execution_id}>
            <button className="quiet" onClick={() => onReplay(run.execution_id)}>
              <span>{new Date(run.ts).toLocaleString()}</span>
              <small>{(run.data.outcome ?? run.data.status ?? 'recorded').replaceAll('_', ' ')}</small>
            </button>
          </li>)}</ul>}
    </section>
  </div>
}
