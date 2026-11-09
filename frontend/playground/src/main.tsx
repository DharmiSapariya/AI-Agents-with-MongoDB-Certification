import { useEffect, useState, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import { errorText, health, json, type Health, type Token, type User } from './api'
import './style.css'

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
  useEffect(() => {
    const controller = new AbortController()
    health(controller.signal).then(setStatus).catch(() => {
      if (!controller.signal.aborted) setHealthFailed(true)
    })
    return () => controller.abort()
  }, [healthCheck])
  useEffect(() => {
    if (!account) return
    const timer = window.setTimeout(() => {
      setAccount(undefined)
      setNotice('Your sign-in expired. Sign in to continue.')
    }, Math.max(0, account.expiresAt - Date.now()))
    return () => window.clearTimeout(timer)
  }, [account])
  const authUnavailable = status?.auth === 'unavailable'
  const badge = healthFailed ? 'Backend offline' : status ? `${status.mode} · ${status.mongodb}` : 'Checking backend'

  return <>
    <header className="topbar">
      <a className="brand" href="#main">MongoDB <span>AI Agents</span></a>
      <div className="top-actions">
        <span className="badge" role="status">{badge}</span>
        {account && <button className="quiet" onClick={() => setAccount(undefined)}>Sign out</button>}
      </div>
    </header>
    <main id="main" className="shell">
      <p className="eyebrow">WORKSPACE / PRIMARY AGENT</p>
      <h1>Agent Playground</h1>
      <p className="intro">Ask about MongoDB, follow the execution, and check the evidence behind the answer.</p>
      {healthFailed && <p className="notice" role="alert">The backend is unavailable. <button className="quiet" onClick={() => {
        setHealthFailed(false)
        setHealthCheck(healthCheck + 1)
      }}>Retry health check</button></p>}
      {status?.status === 'degraded' && <p className="notice" role="status">The backend is running but MongoDB is unavailable.</p>}
      {authUnavailable && <p className="notice" role="status">Account access is unavailable in this configuration. The existing backend page still offers the demo lessons and quiz.</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      {account ? <section className="card"><h2>Workspace</h2><p>Signed in as {account.user.email}.</p></section>
        : <AuthForm disabled={Boolean(authUnavailable || healthFailed)} onSignIn={value => {
          setNotice('')
          setAccount(value)
        }} />}
    </main>
  </>
}

createRoot(document.getElementById('root')!).render(<App />)
