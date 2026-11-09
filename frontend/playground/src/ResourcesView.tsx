import { useState, type ChangeEvent } from 'react'
import { comparisonIssue, parseBenchmark, type BenchmarkReport } from './benchmark'

const repo = 'https://github.com/DharmiSapariya/AI-Agents-with-MongoDB-Certification'
const badge = 'https://www.credly.com/badges/9b5d068b-0566-479f-812b-93b06d01041b'
const curriculum = 'https://github.com/mongodb-university/curriculum/tree/main/AI-Agents-with-MongoDB/01-Building-AI-Agents-with-MongoDB'
const score = (value: number | null) => value === null ? 'Unavailable' : value.toFixed(3)

export function ResourcesView() {
  const [report, setReport] = useState<BenchmarkReport>()
  const [fileName, setFileName] = useState('')
  const [comparison, setComparison] = useState<{ name: string; data: BenchmarkReport }>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function load(event: ChangeEvent<HTMLInputElement>, secondary = false) {
    const input = event.currentTarget
    const file = input.files?.[0]
    if (!file) return
    input.value = ''
    setBusy(true)
    setError('')
    if (secondary) setComparison(undefined)
    else { setReport(undefined); setComparison(undefined) }
    try {
      if (file.size > 1024 * 1024) throw new Error('Choose a JSON report of 1 MB or less.')
      const data = parseBenchmark(await file.text())
      if (secondary) setComparison({ name: file.name, data })
      else { setReport(data); setFileName(file.name) }
    } catch (failure) {
      setError(failure instanceof SyntaxError ? 'The selected file is not valid JSON.'
        : failure instanceof Error ? failure.message : 'Could not read the selected report.')
    } finally {
      setBusy(false)
    }
  }

  const issue = report && comparison ? comparisonIssue(report, comparison.data) : null

  return <div className="resource-grid">
    <section className="card">
      <p className="eyebrow">PROJECT GUIDE</p>
      <h2>Documentation</h2>
      <p>Set up the FastAPI backend, connect Atlas, and run the React workspace locally.</p>
      <ul>
        <li><a href={`${repo}#run`}>Setup and run instructions</a></li>
        <li><a href={`${repo}/blob/main/docs/ARCHITECTURE_DECISIONS.md`}>Architecture decisions</a></li>
        <li><a href={`${repo}/blob/main/docs/IMPLEMENTATION_STATUS.md`}>Implementation and verification status</a></li>
      </ul>
    </section>
    <section className="card">
      <p className="eyebrow">MONGODB UNIVERSITY</p>
      <h2>AI Agents with MongoDB</h2>
      <p>The project accompanies the Building AI Agents with MongoDB course. Mentor progress tracks activities inside this app.</p>
      <ul>
        <li><a href={badge}>View the official credential on Credly</a></li>
        <li><a href={curriculum}>Explore the official course curriculum</a></li>
      </ul>
    </section>
    <section className="card benchmark">
      <p className="eyebrow">RETRIEVAL EVALUATION</p>
      <h2>Benchmark report</h2>
      <p>Load JSON produced by the retrieval evaluator. The file stays in this browser tab.</p>
      <p><a href={`${repo}#live-retrieval-evaluation`}>How to run the evaluator</a></p>
      <label>Evaluation report file<input type="file" accept=".json,application/json" onChange={event => void load(event)} disabled={busy} /></label>
      {error && <p className="error" role="alert">{error}</p>}
      {busy && <p role="status">Reading report…</p>}
      {!report && !busy && <p className="muted">No results loaded. The application does not ship benchmark scores.</p>}
      {report && <>
        <p className="muted wrap">Imported file {fileName} · Mode declared in report {report.mode}</p>
        <dl className="event-detail">
          <dt>Dataset</dt><dd>{report.dataset_version}</dd>
          {report.dataset_sha256 && <><dt>Dataset hash</dt><dd><code>{report.dataset_sha256}</code></dd></>}
          {report.git_sha && <><dt>Revision</dt><dd><code>{report.git_sha}</code></dd></>}
          {report.strategy && <><dt>Strategy</dt><dd>{report.strategy}</dd></>}
          {report.run_id && <><dt>Run ID</dt><dd>{report.run_id}</dd></>}
          <dt>Model</dt><dd>{report.model} · {report.dimensions} dimensions</dd>
          <dt>Index</dt><dd>{report.index} · threshold {report.min_score}</dd>
          <dt>Cases</dt><dd>{report.case_count} total · {report.answerable_count} answerable{report.failed_cases != null && ` · ${report.failed_cases} failed`}</dd>
          <dt>Recall@{report.top_k}</dt><dd>{score(report.recall_at_k)}</dd>
          <dt>MRR@{report.top_k}</dt><dd>{score(report.mrr_at_k)}</dd>
        </dl>
        {report.cases.length > 0 && <div className="table-wrap"><table>
          <thead><tr><th scope="col">Case</th><th scope="col">Recall</th><th scope="col">Reciprocal rank</th>
            <th scope="col">Evidence returned</th><th scope="col">Latency</th></tr></thead>
          <tbody>{report.cases.map(item => <tr key={item.id}><th scope="row">{item.id}</th>
            <td>{score(item.recall)}</td><td>{score(item.reciprocal_rank)}</td>
            <td>{item.error ? `Failed: ${item.error}` : item.returned_no_evidence == null ? 'Unavailable' : item.returned_no_evidence ? 'No' : 'Yes'}</td><td>{item.latency_ms} ms</td></tr>)}</tbody>
        </table></div>}
        <section className="comparison-panel">
          <h3>Compare a second run</h3>
          <label>Comparison report file<input type="file" accept=".json,application/json"
            onChange={event => void load(event, true)} disabled={busy} /></label>
          {issue && <p className="notice" role="status">{issue}</p>}
          {comparison && !issue && <>
            <p className="muted wrap">Comparing {fileName} with {comparison.name}. Metadata matches. Check that both runs used the same corpus snapshot.</p>
            <div className="table-wrap"><table>
              <thead><tr><th scope="col">Run</th><th scope="col">Recall@{report.top_k}</th><th scope="col">MRR@{report.top_k}</th>
                <th scope="col">Failed cases</th></tr></thead>
              <tbody>{[report, comparison.data].map((item, index) => <tr key={index}>
                <th scope="row">{item.strategy ?? (index === 0 ? 'First report' : 'Second report')}</th>
                <td>{score(item.recall_at_k)}</td><td>{score(item.mrr_at_k)}</td>
                <td>{item.failed_cases ?? 'Unavailable'}</td>
              </tr>)}</tbody>
            </table></div>
          </>}
        </section>
        <button className="quiet section-actions" onClick={() => { setReport(undefined); setComparison(undefined); setError('') }}>Clear report</button>
      </>}
    </section>
  </div>
}
