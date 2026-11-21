import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

type SourceRef = { memory_id: string; title: string; page_number: number | null; quote: string }
type Suggestion = {
  id: string
  kind: 'related' | 'relationship' | 'project' | 'tag' | 'collection' | 'entity'
  memory_id: string
  related_memory_id: string | null
  label: string | null
  entity_type: string | null
  source_refs: SourceRef[]
  model: string
  evidence: string
  memory_title: string
  related_title: string | null
}
type Entity = { id: string; name: string; entity_type: string; evidence: string; provenance: string }

export function SuggestionPanel({ projectId, memoryId, onOpen, onChanged }: {
  projectId?: string
  memoryId?: string
  onOpen: (id: string, page?: number | null) => void
  onChanged?: () => void
}) {
  const [items, setItems] = useState<Suggestion[]>([])
  const [entities, setEntities] = useState<Entity[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const scope = projectId ? `project_id=${encodeURIComponent(projectId)}` : `memory_id=${encodeURIComponent(memoryId ?? '')}`
  const load = useCallback(async () => {
    const result = await api<{ items: Suggestion[] }>(`/ai/suggestions?${scope}`)
    setItems(result.items)
    if (memoryId) {
      const linked = await api<{ items: Entity[] }>(`/ai/entities?memory_id=${encodeURIComponent(memoryId)}`)
      setEntities(linked.items)
    }
  }, [scope, memoryId])
  useEffect(() => { void load().catch(() => { setItems([]); setEntities([]) }) }, [load])

  async function act(action: () => Promise<unknown>, failure: string) {
    setBusy(true)
    setError('')
    try {
      await action()
      await load()
      onChanged?.()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : failure)
    } finally {
      setBusy(false)
    }
  }
  function refresh() {
    void act(() => api(`/ai/suggestions/refresh?${scope}`, { method: 'POST' }), 'Could not find suggestions.')
  }
  function analyze(firstId: string, secondId?: string | null) {
    void act(() => api('/ai/suggestions/analyze', {
      method: 'POST', body: JSON.stringify({ memory_id: firstId, related_memory_id: secondId ?? null, project_id: projectId ?? null }),
    }), 'Could not analyze these sources.')
  }
  function review(id: string, decision: 'approve' | 'dismiss') {
    void act(() => api(`/ai/suggestions/${id}/review`, {
      method: 'POST', body: JSON.stringify({ decision }),
    }), 'Could not review suggestion.')
  }
  function removeEntity(id: string) {
    if (memoryId) void act(() => api(`/ai/entities/${memoryId}/${id}`, { method: 'DELETE' }), 'Could not remove entity.')
  }

  return <section className="assist-panel">
    <div className="section-kicker">REVIEW BEFORE ADDING</div>
    <h3>{projectId ? 'Project discoveries' : 'Related memories'}</h3>
    <p>Suggestions are clues from saved text. Open the cited sources before deciding; nothing is added automatically.</p>
    <div className="assist-controls">
      <button className="secondary-button" disabled={busy} onClick={refresh}>{busy ? 'Working...' : 'Find suggestions'}</button>
      {memoryId && <button className="secondary-button" disabled={busy} onClick={() => analyze(memoryId)}>Find named entities</button>}
    </div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {items.map(item => <div className="assist-claim" key={item.id}>
      <span className="assist-kind">{item.kind.replace('_', ' ')}</span>
      <strong>{item.label ? `${item.label.replace('_', ' ')}${item.entity_type ? ` (${item.entity_type})` : ''} for ${item.memory_title}` : item.memory_title}</strong>
      <span>{item.evidence}</span>
      {item.source_refs.length ? item.source_refs.map((ref, index) => <button
        className="assist-citation" key={`${ref.memory_id}-${index}`}
        onClick={() => onOpen(ref.memory_id, ref.page_number)}>
        {ref.title}{ref.page_number ? ` · p. ${ref.page_number}` : ''}: “{ref.quote}”
      </button>) : <>
        <button className="assist-citation" onClick={() => onOpen(item.memory_id)}>Open {item.memory_title}</button>
        {item.related_memory_id && <button className="assist-citation" onClick={() => onOpen(item.related_memory_id!)}>Open {item.related_title}</button>}
      </>}
      <small>{item.model.startsWith('local:') ? 'Local text pattern' : item.kind === 'relationship' || item.kind === 'entity' ? 'Model suggestion · quoted evidence' : 'Embedding similarity'}</small>
      {(item.kind === 'related' || item.kind === 'project') && item.related_memory_id && <button
        className="secondary-button" disabled={busy} onClick={() => analyze(item.memory_id, item.related_memory_id)}>
        Analyze relationship
      </button>}
      <button className="secondary-button" disabled={busy} onClick={() => review(item.id, 'approve')}>Approve</button>
      <button className="secondary-button" disabled={busy} onClick={() => review(item.id, 'dismiss')}>Dismiss</button>
    </div>)}
    {memoryId && entities.length > 0 && <div className="assist-answer">
      <h3>Reviewed entities</h3>
      {entities.map(entity => <div className="assist-claim" key={entity.id}>
        <span className="assist-kind">{entity.entity_type}</span>
        <strong>{entity.name}</strong>
        <span>“{entity.evidence}”</span>
        <small>{entity.provenance === 'reviewed_ai' ? 'Model suggestion approved by you' : entity.provenance}</small>
        <button className="secondary-button" disabled={busy} onClick={() => removeEntity(entity.id)}>Remove</button>
      </div>)}
    </div>}
  </section>
}
