import { useState } from 'react'
import { type Access, useResource } from './resources'

type Summary = {
  window_days: number
  executions: { completed: number; errors: number; retrieval_failures: number; mean_duration_ms: number | null }
  top_tools: { tool: string | null; calls: number; errors: number; mean_duration_ms: number | null }[]
  usage: { reported_calls: number; total_tokens: number | null }
}
const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })
function duration(ms: number | null) {
  return ms == null ? 'Unavailable' : `${number.format(ms)} ms`
}

export function AnalyticsView(access: Access) {
  const [days, setDays] = useState(7)
  const summary = useResource<Summary>(`/api/analytics/summary?days=${days}`, access)
  const data = summary.data

  return <section className="card">
    <div className="section-heading">
      <h2>Recorded activity</h2>
      <div className="button-row">
        <label className="filter">Window<select value={days} onChange={event => setDays(Number(event.target.value))}>
          <option value={1}>Last day</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option>
        </select></label>
        <button className="quiet" onClick={summary.reload}>Refresh</button>
      </div>
    </div>
    <p className="muted">Metrics reflect events recorded for your account in the selected window.</p>
    {summary.error ? <p className="error" role="alert">{summary.error}</p> : !data ? <p>Loading metrics…</p> : <>
      <dl className="metric-grid">
        <div><dt>Finished runs</dt><dd>{number.format(data.executions.completed)}</dd></div>
        <div><dt>Execution errors</dt><dd>{number.format(data.executions.errors)}</dd></div>
        <div><dt>Retrieval failures</dt><dd>{number.format(data.executions.retrieval_failures)}</dd></div>
        <div><dt>Mean run duration</dt><dd>{duration(data.executions.mean_duration_ms)}</dd></div>
        <div><dt>Reported tokens</dt><dd>{data.usage.total_tokens == null ? 'Unavailable' : number.format(data.usage.total_tokens)}</dd>
          <small>{number.format(data.usage.reported_calls)} calls reported usage</small></div>
      </dl>
      <h2>Top tools by recorded calls</h2>
      {data.top_tools.length === 0 ? <p className="muted">No tool calls recorded in this window.</p> :
        <div className="table-wrap"><table>
          <thead><tr><th scope="col">Tool</th><th scope="col">Calls</th><th scope="col">Errors</th><th scope="col">Mean duration</th></tr></thead>
          <tbody>{data.top_tools.map(item => <tr key={item.tool ?? ''}>
            <th scope="row">{item.tool ?? 'Unknown tool'}</th><td>{number.format(item.calls)}</td>
            <td>{number.format(item.errors)}</td><td>{duration(item.mean_duration_ms)}</td>
          </tr>)}</tbody>
        </table></div>}
    </>}
  </section>
}
