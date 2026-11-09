import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import { errorText, health, json, type Health, type Token, type User } from './api'
import { AnalyticsView } from './AnalyticsView'
import { DatabaseExplorer } from './DatabaseExplorer'
import { MentorView } from './MentorView'
import { MemoryStudio } from './MemoryStudio'
import { ExecutionReplay } from './ExecutionReplay'
import { PlatformDashboard, PlatformHome } from './PlatformHome'
import { Playground } from './Playground'
import { ResourcesView } from './ResourcesView'
import './style.css'

type View = 'home' | 'dashboard' | 'playground' | 'executions' | 'memory' | 'explorer' | 'analytics' | 'mentor' | 'resources'
const VIEWS: { id: View; label: string; intro: string }[] = [
  { id: 'home', label: 'Overview', intro: '' },
  { id: 'dashboard', label: 'Dashboard', intro: 'Review your latest runs and recorded activity.' },
  { id: 'playground', label: 'Agent Playground', intro: 'Ask about MongoDB, follow the execution, and check the evidence behind the answer.' },
  { id: 'executions', label: 'Execution Replay', intro: 'Inspect the events recorded during your saved agent runs.' },
  { id: 'memory', label: 'Memory Studio', intro: 'Manage the notes you can opt to share with the agent.' },
  { id: 'explorer', label: 'MongoDB Explorer', intro: 'Browse the collection samples available to your account.' },
  { id: 'analytics', label: 'Analytics', intro: 'Review latency, outcomes, and provider usage from recorded runs.' },
  { id: 'mentor', label: 'Mentor Learning Center', intro: 'Learn from lessons, challenges, and your recorded executions.' },
  { id: 'resources', label: 'Project Resources', intro: 'Find setup guidance, the official credential, and retrieval evaluation reports.' },
]

type Account = { user: User; token: string; expiresAt: number }

function AuthForm({ disabled, onSignIn }: { disabled: boolean; onSignIn: (account: Account) => void }) {
  const [register, setRegister] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    const body = JSON.stringify({ email: fields.get('email'), password: fields.get('password') })
    setBusy(true)
    setError('')
    try {
      if (register) await json<User>('/api/auth/register', { method: 'POST', body })
      const token = await json<Token>('/api/auth/login', { method: 'POST', body })
      const expiresAt = Date.now() + token.expires_in * 1000
      const user = await json<User>('/api/auth/me', {}, token.access_token)
      form.reset()
      onSignIn({ user, token: token.access_token, expiresAt })
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      setBusy(false)
    }
  }

  return <section className="card auth" aria-labelledby="auth-heading">
    <p className="eyebrow">ACCOUNT ACCESS</p>
    <h2 id="auth-heading">{register ? 'Create an account' : 'Sign in'}</h2>
    <form onSubmit={submit}>
      <fieldset disabled={disabled || busy}>
        <label>Email<input type="email" name="email" autoComplete="email" required maxLength={254} /></label>
        <label>Password<input type="password" name="password" required maxLength={128}
          autoComplete={register ? 'new-password' : 'current-password'} minLength={register ? 12 : 1} /></label>
        <button className="primary" type="submit">{busy ? 'Working…' : register ? 'Create account' : 'Sign in'}</button>
      </fieldset>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    <button className="quiet" disabled={disabled || busy} onClick={() => {
      setRegister(!register)
      setError('')
    }}>{register ? 'Already registered? Sign in' : 'New here? Create an account'}</button>
  </section>
}

function App() {
  const [status, setStatus] = useState<Health>()
  const [healthFailed, setHealthFailed] = useState(false)
  const [healthCheck, setHealthCheck] = useState(0)
  const [account, setAccount] = useState<Account>()
  const [notice, setNotice] = useState('')
  const [view, setView] = useState<View>('home')
  const [execution, setExecution] = useState<string>()
  const [mentorSession, setMentorSession] = useState<string>()
  const [mentorExecution, setMentorExecution] = useState<string>()
  const visibleView = account || ['home', 'resources', 'playground'].includes(view) ? view : 'playground'
  const activeView = VIEWS.find(item => item.id === visibleView)!
  const showExecution = (id: string) => { setExecution(id); setView('executions') }
  useEffect(() => {
    const controller = new AbortController()
    health(controller.signal).then(setStatus).catch(() => {
      if (!controller.signal.aborted) setHealthFailed(true)
    })
    return () => controller.abort()
  }, [healthCheck])
  const expire = useCallback(() => {
    setAccount(undefined)
    setNotice('Your sign-in expired. Sign in to continue.')
  }, [])
  useEffect(() => {
    if (!account) return
    const timer = window.setTimeout(expire, Math.max(0, account.expiresAt - Date.now()))
    return () => window.clearTimeout(timer)
  }, [account, expire])
  const authUnavailable = status?.auth === 'unavailable'
  const badge = healthFailed ? 'Backend offline' : status ? `${status.mode} · ${status.mongodb}` : 'Checking backend'

  return <>
    <header className="topbar">
      <button className="brand" onClick={() => setView('home')}>MongoDB <span>AI Agents</span></button>
      <div className="top-actions">
        <span className="badge" role="status">{badge}</span>
        {account && <button className="quiet" onClick={() => setAccount(undefined)}>Sign out</button>}
      </div>
    </header>
    <main id="main" className="shell">
      {visibleView !== 'home' && <>
      <p className="eyebrow">MONGODB AI AGENTS / WORKSPACE</p>
      <h1>{activeView.label}</h1>
      <p className="intro">{activeView.intro}</p></>}
      {healthFailed && <p className="notice" role="alert">The backend is unavailable. <button className="quiet" onClick={() => {
        setHealthFailed(false)
        setHealthCheck(healthCheck + 1)
      }}>Retry health check</button></p>}
      {status?.status === 'degraded' && <p className="notice" role="status">The backend is running but MongoDB is unavailable.</p>}
      {authUnavailable && <p className="notice" role="status">Account access is unavailable in this configuration. The existing backend page still offers the demo lessons and quiz.</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      <nav className="workspace-nav" aria-label="Workspace">
        {VIEWS.filter(item => account || ['home', 'playground', 'resources'].includes(item.id))
          .map(item => <button className="quiet" key={item.id} aria-current={visibleView === item.id ? 'page' : undefined}
            onClick={() => setView(item.id)}>{item.label}</button>)}
      </nav>
      {visibleView === 'home' && <PlatformHome onOpen={() => setView(account ? 'dashboard' : 'playground')}
        onResources={() => setView('resources')} />}
      {visibleView === 'resources' && <ResourcesView />}
      {account ? <>
        {view === 'dashboard' && <PlatformDashboard token={account.token} onExpired={expire}
          onOpen={() => setView('playground')} onReplay={showExecution} />}
        <div hidden={view !== 'playground'}>
          <Playground token={account.token} email={account.user.email} onExpired={expire} onInspect={showExecution} />
        </div>
        {view === 'executions' && <ExecutionReplay token={account.token} onExpired={expire}
          selected={execution} onSelect={setExecution} onMentor={id => {
            setMentorExecution(id)
            setView('mentor')
          }} />}
        {view === 'memory' && <MemoryStudio token={account.token} onExpired={expire} />}
        {view === 'explorer' && <DatabaseExplorer token={account.token} onExpired={expire} />}
        {view === 'analytics' && <AnalyticsView token={account.token} onExpired={expire} />}
        {view === 'mentor' && <MentorView token={account.token} onExpired={expire}
          session={mentorSession} onSession={setMentorSession} initialExecution={mentorExecution} />}
      </>
        : visibleView === 'playground' && <AuthForm disabled={Boolean(authUnavailable || healthFailed)} onSignIn={value => {
          setNotice('')
          setView('dashboard')
          setExecution(undefined)
          setMentorSession(undefined)
          setMentorExecution(undefined)
          setAccount(value)
        }} />}
    </main>
  </>
}

createRoot(document.getElementById('root')!).render(<App />)
