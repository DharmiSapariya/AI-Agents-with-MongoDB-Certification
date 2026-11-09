import { useState, type FormEvent } from 'react'
import { ApiError, errorText, request } from './api'
import { type Access, useResource } from './resources'

type Note = { id: string; text: string; created_at: string }

export function MemoryStudio(access: Access) {
  const [skip, setSkip] = useState(0)
  const notes = useResource<Note[]>(`/api/memory?limit=11&skip=${skip}`, access)
  const [text, setText] = useState('')
  const [confirm, setConfirm] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  async function change(path: string, options: RequestInit, onSuccess: () => void) {
    setBusy(true)
    setStatus('')
    setError('')
    try {
      await request(path, options, access.token)
      onSuccess()
      notes.reload()
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) access.onExpired()
      else setError(errorText(failure))
    } finally {
      setBusy(false)
    }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !text.trim()) return
    void change('/api/memory', { method: 'POST', body: JSON.stringify({ text: text.trim() }) }, () => {
      setText('')
      setSkip(0)
      setStatus('Note saved.')
    })
  }

  return <div className="workspace">
    <section className="card">
      <h2>Save a note</h2>
      <p className="muted">Chat uses notes when you enable saved notes for that turn.</p>
      <form className="composer" onSubmit={save}>
        <label>Personalization note<textarea value={text} onChange={event => setText(event.target.value)}
          maxLength={500} required rows={4} disabled={busy} /></label>
        <button className="primary" disabled={busy || !text.trim()} type="submit">Save note</button>
      </form>
      {status && <p role="status">{status}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
    <section className="card">
      <h2>Your saved notes</h2>
      {notes.error ? <p className="error" role="alert">{notes.error}</p> : !notes.data ? <p>Loading notes…</p>
        : !notes.data.length ? <p className="muted">No notes on this page.</p>
        : notes.data.slice(0, 10).map(note => <article className="turn" key={note.id}>
          <p>{note.text}</p><p className="muted">{new Date(note.created_at).toLocaleString()}</p>
          {confirm === note.id ? <div className="button-row">
            <button className="quiet" disabled={busy} onClick={() => {
              void change(`/api/memory/${encodeURIComponent(note.id)}`, { method: 'DELETE' }, () => {
                setConfirm(undefined)
                setStatus('Note deleted.')
              })
            }}>Confirm deletion</button>
            <button className="quiet" disabled={busy} onClick={() => setConfirm(undefined)}>Cancel</button>
          </div> : <button className="quiet" disabled={busy} onClick={() => setConfirm(note.id)}>Delete note</button>}
        </article>)}
      <div className="button-row section-actions">
        <button className="quiet" disabled={busy || skip === 0} onClick={() => setSkip(skip - 10)}>Previous page</button>
        <button className="quiet" disabled={busy || (notes.data?.length ?? 0) <= 10 || skip >= 1000}
          onClick={() => setSkip(skip + 10)}>Next page</button>
        <button className="quiet" disabled={busy} onClick={notes.reload}>Refresh</button>
      </div>
    </section>
  </div>
}
