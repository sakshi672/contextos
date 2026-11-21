import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

type Suggestion = { id: string; kind: 'related' | 'project'; memory_id: string; related_memory_id: string; evidence: string; memory_title: string; related_title: string }

export function SuggestionPanel({ projectId, memoryId, onOpen, onChanged }: { projectId?: string; memoryId?: string; onOpen: (id: string) => void; onChanged?: () => void }) {
  const [items, setItems] = useState<Suggestion[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const scope = projectId ? `project_id=${encodeURIComponent(projectId)}` : `memory_id=${encodeURIComponent(memoryId ?? '')}`
  const load = useCallback(async () => { const result = await api<{ items: Suggestion[] }>(`/ai/suggestions?${scope}`); setItems(result.items) }, [scope])
  useEffect(() => { void load().catch(() => setItems([])) }, [load])
  async function refresh() { setBusy(true); setError(''); try { await api(`/ai/suggestions/refresh?${scope}`, { method: 'POST' }); await load() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not find suggestions.') } finally { setBusy(false) } }
  async function review(id: string, decision: 'approve' | 'dismiss') { setBusy(true); setError(''); try { await api(`/ai/suggestions/${id}/review`, { method: 'POST', body: JSON.stringify({ decision }) }); await load(); onChanged?.() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not review suggestion.') } finally { setBusy(false) } }
  return <section className="assist-panel"><div className="section-kicker">REVIEW BEFORE ADDING</div><h3>{projectId ? 'Memories for this project' : 'Related memories'}</h3><p>Similarity suggests a connection; open both memories to decide. Nothing is added without your approval.</p><button className="secondary-button" disabled={busy} onClick={() => void refresh()}>{busy ? 'Working…' : 'Find suggestions'}</button>{error && <p className="inline-error" role="alert">{error}</p>}{items.map(item => <div className="assist-claim" key={item.id}><button className="assist-citation" onClick={() => onOpen(item.memory_id)}>{item.memory_title}</button><span>{item.evidence}</span><button className="assist-citation" onClick={() => onOpen(item.related_memory_id)}>{item.related_title}</button><button className="secondary-button" disabled={busy} onClick={() => void review(item.id, 'approve')}>Approve</button><button className="secondary-button" disabled={busy} onClick={() => void review(item.id, 'dismiss')}>Dismiss</button></div>)}</section>
}
