import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, GitBranch, List, Plus, Search, Trash2 } from 'lucide-react'
import { api } from './api'
import type { Organization } from './Organization'

type Relation = { id: string; from_memory_id: string; to_memory_id: string; from_title: string; to_title: string; relation_type: string; explanation: string; provenance: string }
type Memory = { id: string; title: string; kind: string; captured_at: string }
type Page<T> = { items: T[]; total: number }
type Graph = { nodes: { id: string; title: string; kind: string }[]; edges: Relation[]; truncated: boolean }
const relationTypes = ['related', 'supports', 'contradicts', 'inspired_by', 'references']
const kinds = ['all', 'note', 'link', 'web_page', 'snippet', 'pdf', 'document', 'image']
const label = (value: string) => value.replaceAll('_', ' ')
const date = (value: string) => new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

function RelationRow({ relation, onOpen, onChanged }: { relation: Relation; onOpen: (id: string) => void; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [type, setType] = useState(relation.relation_type)
  const [explanation, setExplanation] = useState(relation.explanation)
  const [error, setError] = useState('')
  async function save() {
    try { await api(`/relationships/${relation.id}`, { method: 'PATCH', body: JSON.stringify({ relation_type: type, explanation }) }); setEditing(false); onChanged() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save connection.') }
  }
  async function remove() {
    if (!window.confirm('Remove this connection?')) return
    try { await api(`/relationships/${relation.id}`, { method: 'DELETE' }); onChanged() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not remove connection.') }
  }
  return <article className="explore-relation">
    <div className="explore-relation-main"><button onClick={() => onOpen(relation.from_memory_id)}>{relation.from_title}</button><span>{label(relation.relation_type)}</span><button onClick={() => onOpen(relation.to_memory_id)}>{relation.to_title}</button></div>
    {editing ? <div className="explore-form"><select aria-label="Connection type" value={type} onChange={e => setType(e.target.value)}>{relationTypes.map(value => <option key={value} value={value}>{label(value)}</option>)}</select><textarea aria-label="Connection explanation" value={explanation} maxLength={2000} onChange={e => setExplanation(e.target.value)} /><div><button className="primary-button" disabled={!explanation.trim()} onClick={() => void save()}>Save</button><button className="secondary-button" onClick={() => setEditing(false)}>Cancel</button></div></div> : <p>{relation.explanation}</p>}
    <div className="explore-relation-foot"><small>{relation.provenance === 'manual' ? 'Added by you' : label(relation.provenance)}</small><button onClick={() => setEditing(true)}>Edit</button><button onClick={() => void remove()} aria-label="Remove connection"><Trash2 size={15} /></button></div>{error && <p className="inline-error" role="alert">{error}</p>}
  </article>
}

export function ConnectionsView({ organization, onOpen, memoryId, projectId }: { organization: Organization; onOpen: (id: string) => void; memoryId?: string; projectId?: string }) {
  const [scope, setScope] = useState(projectId ?? '')
  const [mode, setMode] = useState<'graph' | 'list'>(memoryId ? 'list' : 'graph')
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [], truncated: false })
  const [rows, setRows] = useState<Relation[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [from, setFrom] = useState(memoryId ?? '')
  const [to, setTo] = useState('')
  const [type, setType] = useState('related')
  const [explanation, setExplanation] = useState('')
  const [search, setSearch] = useState('')
  const [choices, setChoices] = useState<Memory[]>([])
  const [chosen, setChosen] = useState<Record<string, Memory>>({})
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  useEffect(() => { setScope(projectId ?? '') }, [projectId])
  useEffect(() => { setFrom(memoryId ?? '') }, [memoryId])
  const refresh = useCallback(() => setVersion(value => value + 1), [])
  useEffect(() => {
    let live = true
    const params = new URLSearchParams({ limit: '100' })
    if (scope) params.set('project_id', scope)
    api<Graph>(`/relationships/graph?${params}`).then(value => { if (live) setGraph(value) }).catch(cause => { if (live) setError(cause.message) })
    const listParams = new URLSearchParams({ limit: '50', offset: String(offset) })
    if (scope) listParams.set('project_id', scope)
    if (memoryId) listParams.set('memory_id', memoryId)
    api<Page<Relation>>(`/relationships?${listParams}`).then(value => { if (live) { setRows(value.items); setTotal(value.total) } }).catch(cause => { if (live) setError(cause.message) })
    return () => { live = false }
  }, [scope, memoryId, offset, version])
  useEffect(() => {
    let live = true
    const q = search.trim()
    if (!q) { setChoices([]); return }
    const timer = window.setTimeout(() => { api<Page<Memory>>(`/search?${new URLSearchParams({ q, limit: '12' })}`).then(value => { if (live) setChoices(value.items) }).catch(() => { if (live) setChoices([]) }) }, 220)
    return () => { live = false; window.clearTimeout(timer) }
  }, [search])
  async function create() {
    setError('')
    try { await api('/relationships', { method: 'POST', body: JSON.stringify({ from_memory_id: from, to_memory_id: to, relation_type: type, explanation }) }); setExplanation(''); setTo(''); setSearch(''); refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not add connection.') }
  }
  const graphEdges = memoryId ? graph.edges.filter(edge => edge.from_memory_id === memoryId || edge.to_memory_id === memoryId) : graph.edges
  const graphNodes = graph.nodes.filter(node => !memoryId || graphEdges.some(edge => edge.from_memory_id === node.id || edge.to_memory_id === node.id))
  const options = [...new Map([...Object.values(chosen), ...choices].map(item => [item.id, item])).values()]
  return <section className="explore-stack">
    <div className="explore-toolbar"><select aria-label="Filter connections by project" value={scope} onChange={e => { setScope(e.target.value); setOffset(0) }}><option value="">All projects</option>{organization.projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select><div className="explore-switch" role="group" aria-label="Connection view"><button className={mode === 'graph' ? 'active' : ''} onClick={() => setMode('graph')}><GitBranch size={16} /> Graph</button><button className={mode === 'list' ? 'active' : ''} onClick={() => setMode('list')}><List size={16} /> List</button></div></div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {mode === 'graph' ? <div className="explore-graph" role="region" aria-label="Memory connection graph">{graphNodes.length ? <div className="explore-graph-canvas"><svg viewBox="0 0 800 500" role="img" aria-label={`${graphNodes.length} memories and ${graphEdges.length} connections`}><defs><marker id="explore-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#a6afa9" /></marker></defs>{graphEdges.map(edge => { const a = graphNodes.findIndex(node => node.id === edge.from_memory_id); const b = graphNodes.findIndex(node => node.id === edge.to_memory_id); if (a < 0 || b < 0) return null; const pos = (i: number) => ({ x: 400 + 295 * Math.cos(2 * Math.PI * i / graphNodes.length), y: 250 + 185 * Math.sin(2 * Math.PI * i / graphNodes.length) }); const p = pos(a), q = pos(b); return <line key={edge.id} x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke="#a6afa9" strokeWidth="1.5" markerEnd="url(#explore-arrow)" /> })}{graphNodes.map((node, i) => { const x = 400 + 295 * Math.cos(2 * Math.PI * i / graphNodes.length), y = 250 + 185 * Math.sin(2 * Math.PI * i / graphNodes.length); return <g key={node.id} role="button" tabIndex={0} onClick={() => onOpen(node.id)} onKeyDown={e => { if (e.key === 'Enter') onOpen(node.id) }} aria-label={`Open ${node.title}`} className="explore-node"><rect x={x - 82} y={y - 27} width="164" height="54" rx="13" /><text x={x} y={y - 2} textAnchor="middle">{node.title.length > 23 ? `${node.title.slice(0, 22)}…` : node.title}</text><text x={x} y={y + 15} textAnchor="middle" className="explore-node-kind">{label(node.kind)}</text></g> })}</svg></div> : <p className="explore-empty">Connect two memories to start your graph.</p>}{graph.truncated && <p className="explore-hint">Showing the 100 most recent connections. Use the list for more.</p>}<p className="explore-hint">Select a memory to open it. Switch to List to read explanations or edit connections.</p></div> : <div>{rows.length ? rows.map(row => <RelationRow key={row.id} relation={row} onOpen={onOpen} onChanged={refresh} />) : <p className="explore-empty">No connections in this view yet.</p>}{total > 50 && <div className="explore-pages"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><span>{offset + 1}–{Math.min(offset + 50, total)} of {total}</span><button disabled={offset + 50 >= total} onClick={() => setOffset(offset + 50)}>Next</button></div>}</div>}
    <section className="explore-create"><div className="section-kicker">CONNECT YOUR CONTEXT</div><h3>Add a connection</h3><p>Explain how these memories relate. The direction matters for supports, references, and inspired by.</p><div className="explore-form"><label className="explore-search"><Search size={16} /><input aria-label="Find memories to connect" placeholder="Search memories to choose from…" value={search} onChange={e => setSearch(e.target.value)} /></label><div className="explore-two"><label>From memory<select value={from} onChange={e => { setFrom(e.target.value); const item = options.find(option => option.id === e.target.value); if (item) setChosen(value => ({ ...value, [item.id]: item })) }}><option value="">Select a memory</option>{memoryId && !options.some(item => item.id === memoryId) && <option value={memoryId}>Current memory</option>}{options.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><label>To memory<select value={to} onChange={e => { setTo(e.target.value); const item = options.find(option => option.id === e.target.value); if (item) setChosen(value => ({ ...value, [item.id]: item })) }}><option value="">Select a memory</option>{options.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label></div><label>Relationship<select value={type} onChange={e => setType(e.target.value)}>{relationTypes.map(value => <option key={value} value={value}>{label(value)}</option>)}</select></label><label>Why are they connected?<textarea value={explanation} maxLength={2000} onChange={e => setExplanation(e.target.value)} placeholder="A short explanation your future self will understand" /></label><button className="primary-button" disabled={!from || !to || from === to || !explanation.trim()} onClick={() => void create()}><Plus size={16} /> Add connection</button></div></section>
  </section>
}

export function TimelineView({ organization, onOpen, projectId }: { organization: Organization; onOpen: (id: string) => void; projectId?: string }) {
  const [scope, setScope] = useState(projectId ?? '')
  const [kind, setKind] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<Page<Memory>>({ items: [], total: 0 })
  const [error, setError] = useState('')
  useEffect(() => { setScope(projectId ?? '') }, [projectId])
  useEffect(() => { let live = true; const params = new URLSearchParams({ kind, limit: '50', offset: String(offset) }); if (scope) params.set('project_id', scope); if (from) params.set('date_from', from); if (to) params.set('date_to', to); api<Page<Memory>>(`/timeline?${params}`).then(value => { if (live) { setData(value); setError('') } }).catch(cause => { if (live) setError(cause.message) }); return () => { live = false } }, [scope, kind, from, to, offset])
  return <section className="explore-stack"><div className="explore-toolbar"><select aria-label="Timeline project" value={scope} onChange={e => { setScope(e.target.value); setOffset(0) }}><option value="">All projects</option>{organization.projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><select aria-label="Timeline type" value={kind} onChange={e => { setKind(e.target.value); setOffset(0) }}>{kinds.map(value => <option key={value} value={value}>{label(value)}</option>)}</select><label>From <input type="date" value={from} onChange={e => { setFrom(e.target.value); setOffset(0) }} /></label><label>To <input type="date" value={to} onChange={e => { setTo(e.target.value); setOffset(0) }} /></label></div>{error && <div className="inline-error" role="alert">{error}</div>}{data.items.length ? <div className="explore-timeline">{data.items.map(item => <button key={item.id} className="explore-timeline-item" onClick={() => onOpen(item.id)}><span className="explore-timeline-date">{date(item.captured_at)}</span><span><strong>{item.title}</strong><small>{label(item.kind)}</small></span><ArrowRight size={16} /></button>)}</div> : <p className="explore-empty">No memories match this timeline.</p>}{data.total > 50 && <div className="explore-pages"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><span>{offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}</span><button disabled={offset + 50 >= data.total} onClick={() => setOffset(offset + 50)}>Next</button></div>}</section>
}

export function ProjectOverview({ projectId, organization, onOpen, onSearch, refreshKey = 0 }: { projectId: string; organization: Organization; onOpen: (id: string) => void; onSearch: () => void; refreshKey?: number }) {
  const [overview, setOverview] = useState<{ project: { name: string }; memory_count: number; connection_count: number; recent_memories: Memory[] } | null>(null)
  const [tab, setTab] = useState<'memories' | 'timeline' | 'connections'>('memories')
  const [error, setError] = useState('')
  useEffect(() => { let live = true; api<typeof overview>(`/projects/${projectId}/overview`).then(value => { if (live) setOverview(value) }).catch(cause => { if (live) setError(cause.message) }); return () => { live = false } }, [projectId, refreshKey])
  return <section className="explore-stack">{error && <div className="inline-error" role="alert">{error}</div>}{overview && <><div className="explore-project-head"><div><div className="section-kicker">PROJECT OVERVIEW</div><h2>{overview.project.name}</h2><p>{overview.memory_count} memories · {overview.connection_count} connections</p></div><button className="secondary-button" onClick={onSearch}><Search size={16} /> Search this project</button></div><div className="explore-switch" role="tablist" aria-label="Project sections"><button className={tab === 'memories' ? 'active' : ''} onClick={() => setTab('memories')}>Memories</button><button className={tab === 'timeline' ? 'active' : ''} onClick={() => setTab('timeline')}>Timeline</button><button className={tab === 'connections' ? 'active' : ''} onClick={() => setTab('connections')}>Connections</button></div>{tab === 'memories' && <div>{overview.recent_memories.map(item => <button className="explore-timeline-item" key={item.id} onClick={() => onOpen(item.id)}><span><strong>{item.title}</strong><small>{label(item.kind)} · {date(item.captured_at)}</small></span><ArrowRight size={16} /></button>)}{!overview.recent_memories.length && <p className="explore-empty">No memories in this project yet.</p>}{overview.memory_count > 20 && <button className="secondary-button" onClick={onSearch}>Browse all memories</button>}</div>}{tab === 'timeline' && <TimelineView organization={organization} projectId={projectId} onOpen={onOpen} />}{tab === 'connections' && <ConnectionsView organization={organization} projectId={projectId} onOpen={onOpen} />}</>}</section>
}
