import { useState } from 'react'

export type View = 'home' | 'dashboard' | 'playground' | 'executions' | 'memory' | 'explorer' | 'analytics' | 'mentor' | 'resources'
export type ViewItem = { id: View; label: string; intro: string }

const groups: { label: string; views: View[] }[] = [
  { label: 'Workspace', views: ['home', 'dashboard', 'playground', 'executions'] },
  { label: 'Data', views: ['memory', 'explorer', 'analytics'] },
  { label: 'Learn and evaluate', views: ['mentor', 'resources'] },
]

export function WorkspaceNavigation({ items, current, navigate }: {
  items: ViewItem[]; current: View; navigate: (view: View) => void
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [query, setQuery] = useState('')
  const available = items.filter(item => item.label.toLowerCase().includes(query.trim().toLowerCase()))
  return <aside className="workspace-rail">
    <button className="quiet rail-toggle" aria-expanded={!collapsed} aria-controls="workspace-menu"
      onClick={() => setCollapsed(value => !value)}>{collapsed ? 'Show navigation' : 'Collapse navigation'}</button>
    <nav id="workspace-menu" aria-label="Workspace" hidden={collapsed}>
      <label className="rail-search">Find a page<input type="search" value={query}
        onChange={event => setQuery(event.target.value)} placeholder="Search workspace" /></label>
      {groups.map(group => {
        const pages = group.views.flatMap(id => available.filter(item => item.id === id))
        return pages.length > 0 && <section key={group.label}>
          <p className="eyebrow">{group.label}</p>
          {pages.map(item => <button key={item.id} className="quiet"
            aria-current={current === item.id ? 'page' : undefined}
            onClick={() => { navigate(item.id); setQuery('') }}>{item.label}</button>)}
        </section>
      })}
      {!available.length && <p className="muted">No matching pages.</p>}
    </nav>
  </aside>
}
