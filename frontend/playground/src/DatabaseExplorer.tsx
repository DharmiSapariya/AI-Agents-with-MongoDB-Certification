import { useState } from 'react'
import { type Access, useResource } from './resources'

type Collection = { name: string; scope: string; count: number }
type Sample = { _id: string } & Record<string, unknown>

export function DatabaseExplorer(access: Access) {
  const [selection, setSelection] = useState('')
  const [skip, setSkip] = useState(0)
  const collections = useResource<Collection[]>('/api/db/collections', access)
  const current = collections.data?.find(item => item.name === selection) ?? collections.data?.[0]
  const sample = useResource<Sample[]>(current ? `/api/db/sample/${encodeURIComponent(current.name)}?limit=11&skip=${skip}` : null, access)

  return <div className="workspace">
    <section className="card">
      <h2>Collections</h2>
      {collections.error ? <p className="error" role="alert">{collections.error}</p>
        : !collections.data ? <p>Loading collections…</p>
        : !collections.data.length ? <p className="muted">No collections are available.</p>
        : <ul className="session-list">{collections.data.map(item => <li key={item.name}>
          <button className="quiet" aria-pressed={current?.name === item.name}
            onClick={() => { setSelection(item.name); setSkip(0) }}>
            <span>{item.name}</span><small>{item.count}</small>
          </button>
        </li>)}</ul>}
      <button className="quiet" onClick={() => { collections.reload(); sample.reload() }}>Refresh</button>
    </section>
    <section className="card">
      <h2>{current?.name ?? 'Collection sample'}</h2>
      {current && <p className="muted">{current.scope === 'owned' ? 'Your records' : 'Shared catalog'} · {current.count} records</p>}
      {sample.error ? <p className="error" role="alert">{sample.error}</p> : current && !sample.data ? <p>Loading sample…</p>
        : sample.data?.length === 0 ? <p className="muted">No records on this page.</p>
        : sample.data?.slice(0, 10).map(item => <details className="citations" key={item._id}>
          <summary>{item._id}</summary><pre className="record">{JSON.stringify(item, null, 2)}</pre>
        </details>)}
      {current && <div className="button-row section-actions">
        <button className="quiet" disabled={skip === 0} onClick={() => setSkip(skip - 10)}>Previous page</button>
        <button className="quiet" disabled={(sample.data?.length ?? 0) <= 10 || skip >= 1000}
          onClick={() => setSkip(skip + 10)}>Next page</button>
      </div>}
    </section>
  </div>
}
