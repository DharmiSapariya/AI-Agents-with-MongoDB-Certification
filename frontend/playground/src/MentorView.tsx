import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, errorText, json } from './api'
import { type Access, useResource } from './resources'

const lessons = [
  ['agent', 'AI agents'], ['tools', 'Tools and function calling'], ['langgraph', 'LangGraph'],
  ['memory', 'Memory'], ['vector_search', 'Vector search'], ['observability', 'Observability'],
]
const modes = [
  ['teach', 'Learn a concept'], ['watch', 'Watch a trace'], ['step', 'Step through a trace'],
  ['quiz', 'Take the quiz'], ['challenge', 'Try a challenge'],
] as const
type Mode = typeof modes[number][0]
type Question = { id: string; q: string; options: string[] }
type Challenge = { id: string; title: string; task: string; options: string[]; file: string }
type Step = { seq: number; type: string; node: string | null; recorded: Record<string, unknown>; interpretation: string }
type Progress = { lessons_viewed: string[]; quiz: { attempts: number; best_score: number | null }; challenges_passed: string[] }
type Run = {
  session_id: string; run_id: string; lesson?: { title: string; text: string; file: string; exercise: string; official: boolean }
  steps?: Step[]; step?: Step | null; has_more?: boolean; truncated?: boolean
  score?: number; total?: number; results?: { id: string; correct: boolean; why: string }[]
  passed?: boolean; file?: string
}
type History = { run_id: string; mode: Mode; created_at: string }

function TraceStep({ step }: { step: Step }) {
  return <article className="turn">
    <strong>{step.seq}. {step.type}{step.node && ` · ${step.node}`}</strong>
    <p>{step.interpretation}</p>
    <details className="citations"><summary>Recorded metadata</summary>
      <pre className="record">{JSON.stringify(step.recorded, null, 2)}</pre>
    </details>
  </article>
}

export function MentorView({ session, onSession, initialExecution, ...access }: Access & {
  session?: string; onSession: (id: string | undefined) => void; initialExecution?: string
}) {
  const [mode, setMode] = useState<Mode>(initialExecution ? 'watch' : 'teach')
  const [concept, setConcept] = useState('agent')
  const [execution, setExecution] = useState(initialExecution ?? '')
  const [resume, setResume] = useState('')
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [challengeId, setChallengeId] = useState('')
  const [choice, setChoice] = useState<number>()
  const [result, setResult] = useState<Run>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  const quiz = useResource<Question[]>(mode === 'quiz' ? '/api/mentor/quiz' : null, access)
  const challenges = useResource<Challenge[]>(mode === 'challenge' ? '/api/mentor/challenges' : null, access)
  const progress = useResource<Progress>('/api/mentor/progress', access)
  const history = useResource<History[]>(session ? `/api/mentor/sessions/${encodeURIComponent(session)}?limit=10` : null, access)
  const challenge = challenges.data?.find(item => item.id === challengeId) ?? challenges.data?.[0]
  const traceMode = mode === 'watch' || mode === 'step'
  const loadError = mode === 'quiz' ? quiz.error : mode === 'challenge' ? challenges.error : undefined
  useEffect(() => () => active.current?.abort(), [])

  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    const payload: Record<string, unknown> = { mode, session_id: session }
    if (mode === 'teach') payload.concept = concept
    if (traceMode) payload.execution_id = execution.trim()
    if (mode === 'step' && result?.step) payload.after_seq = result.step.seq
    if (mode === 'quiz') payload.answers = answers
    if (mode === 'challenge') {
      payload.challenge_id = challenge?.id
      payload.choice = choice
    }
    try {
      const next = await json<Run>('/api/mentor/run', {
        method: 'POST', signal: controller.signal, body: JSON.stringify(payload),
      }, access.token)
      if (controller.signal.aborted) return
      onSession(next.session_id)
      setResult(next)
      progress.reload()
      history.reload()
    } catch (failure) {
      if (controller.signal.aborted) return
      if (failure instanceof ApiError && failure.status === 401) access.onExpired()
      else setError(errorText(failure))
    } finally {
      active.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  function resumeSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSession(resume.trim())
    setResult(undefined)
    setError('')
  }

  return <div className="workspace">
    <aside className="card">
      <h2>Learning progress</h2>
      {progress.error ? <p className="error" role="alert">{progress.error}</p> : progress.data ? <>
        <p>{progress.data.lessons_viewed.length} lessons viewed</p>
        <p>{progress.data.quiz.attempts} quiz attempts · Best: {progress.data.quiz.best_score ?? '—'}</p>
        <p>{progress.data.challenges_passed.length} challenges passed</p>
      </> : <p>Loading progress…</p>}
      <h2>Mentor session</h2>
      <p className="muted wrap">{session ?? 'A session starts with your first activity.'}</p>
      {session && <button className="quiet" disabled={busy} onClick={() => {
        onSession(undefined)
        setResult(undefined)
        setError('')
      }}>New Mentor session</button>}
      <form className="composer" onSubmit={resumeSession}>
        <label>Resume by session ID<input value={resume} pattern="mtr_[0-9a-f]{32}" required
          disabled={busy} onChange={event => setResume(event.target.value)} /></label>
        <button className="quiet" disabled={busy || !resume} type="submit">Resume session</button>
      </form>
      {history.error && <p className="error" role="alert">{history.error}</p>}
      {session && !history.data && !history.error && <p className="muted">Loading session activity…</p>}
      {history.data && <ul className="session-list">{history.data.map(item =>
        <li key={item.run_id}>{item.mode} · {new Date(item.created_at).toLocaleString()}</li>)}</ul>}
    </aside>
    <section className="card">
      <h2>Mentor activities</h2>
      <form className="composer" onSubmit={run}>
        <fieldset disabled={busy}>
          <label>Activity<select value={mode} onChange={event => {
            setMode(event.target.value as Mode)
            setResult(undefined)
            setError('')
          }}>{modes.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          {mode === 'teach' && <label>Concept<select value={concept} onChange={event => setConcept(event.target.value)}>
            {lessons.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select></label>}
          {traceMode && <label>Primary execution ID<input required maxLength={64} value={execution}
            onChange={event => { setExecution(event.target.value); setResult(undefined) }} /></label>}
          {mode === 'quiz' && (quiz.data ? quiz.data.map(question => <label key={question.id}>{question.q}
            <select required value={answers[question.id] ?? ''} onChange={event => {
              const value = event.target.value
              setAnswers(previous => {
                const next = { ...previous }
                if (value === '') delete next[question.id]
                else next[question.id] = Number(value)
                return next
              })
            }}><option value="">Choose an answer</option>{question.options.map((option, i) =>
              <option value={i} key={option}>{option}</option>)}</select>
          </label>) : !loadError && <p>Loading quiz…</p>)}
          {mode === 'challenge' && (challenge ? <>
            <label>Challenge<select value={challenge.id} onChange={event => {
              setChallengeId(event.target.value); setChoice(undefined); setResult(undefined)
            }}>{challenges.data?.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
            <p>{challenge.task} <code>{challenge.file}</code></p>
            <label>Your answer<select required value={choice ?? ''} onChange={event =>
              setChoice(event.target.value === '' ? undefined : Number(event.target.value))}>
              <option value="">Choose an answer</option>{challenge.options.map((option, i) =>
                <option value={i} key={option}>{option}</option>)}</select></label>
          </> : !loadError && <p>Loading challenges…</p>)}
          <button className="primary" type="submit" disabled={(mode === 'quiz' && !quiz.data) ||
            (mode === 'challenge' && !challenge) || (mode === 'step' && result !== undefined && !result.has_more)}>
            {busy ? 'Running…' : mode === 'step' && result?.step ? 'Next recorded step' : 'Run activity'}
          </button>
          {mode === 'step' && result && <button type="button" className="quiet" onClick={() => setResult(undefined)}>Reset walkthrough</button>}
        </fieldset>
      </form>
      {(error || loadError) && <p className="error" role="alert">{error || loadError}</p>}
      {result?.lesson && <article className="turn"><h3>{result.lesson.title}</h3><p>{result.lesson.text}</p>
        <p>{result.lesson.exercise}</p><p className="muted">{result.lesson.official ? 'Course topic' : 'Project extension'}</p></article>}
      {result?.steps?.map(step => <TraceStep key={step.seq} step={step} />)}
      {result?.truncated && <p className="muted">The overview shows the first 100 events. Use step mode to continue.</p>}
      {result?.step && <TraceStep step={result.step} />}
      {mode === 'step' && result && !result.has_more && <p className="muted">End of the recorded trace.</p>}
      {result?.score !== undefined && <section><h3>Score {result.score} / {result.total}</h3>
        <ul>{result.results?.map(item => <li key={item.id}>{item.id}: {item.correct ? 'Correct' : 'Incorrect'} · {item.why}</li>)}</ul></section>}
      {result?.passed !== undefined && <p role="status">{result.passed ? 'Challenge passed.' : 'Try again after inspecting the source.'}</p>}
    </section>
  </div>
}
