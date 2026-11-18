import { useEffect, useState } from 'react'
import { ArrowRight, Check, Plus, Trash2, X } from 'lucide-react'
import { api } from './api'

export type OrgEntity = 'projects' | 'collections' | 'tags'
export type OrgItem = { id: string; name: string; memory_count?: number }
export type Organization = Record<OrgEntity, OrgItem[]>
export const emptyOrganization: Organization = { projects: [], collections: [], tags: [] }
const labels: Record<OrgEntity, string> = { projects: 'Projects', collections: 'Collections', tags: 'Tags' }
const groups: OrgEntity[] = ['projects', 'collections', 'tags']

export function OrganizationView({ data, refresh, onScope }: {
  data: Organization; refresh: () => Promise<void>;
  onScope: (entity: OrgEntity, id: string) => void
}) {
  const [drafts, setDrafts] = useState<Record<OrgEntity, string>>({ projects: '', collections: '', tags: '' })
  const [editing, setEditing] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function create(entity: OrgEntity) {
    const name = drafts[entity].trim()
    if (!name) return
    setBusy(true); setError('')
    try {
      await api(`/organization/${entity}`, { method: 'POST', body: JSON.stringify({ name }) })
      setDrafts(value => ({ ...value, [entity]: '' }))
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create item.') }
    finally { setBusy(false) }
  }

  async function rename(entity: OrgEntity, id: string) {
    setBusy(true); setError('')
    try {
      await api(`/organization/${entity}/${id}`, { method: 'PATCH', body: JSON.stringify({ name: editName }) })
      setEditing(null)
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not rename item.') }
    finally { setBusy(false) }
  }

  async function remove(entity: OrgEntity, item: OrgItem) {
    if (!window.confirm(`Delete ${item.name}? Memories assigned to it will remain in your library.`)) return
    setBusy(true); setError('')
    try {
      await api(`/organization/${entity}/${item.id}`, { method: 'DELETE' })
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete item.') }
    finally { setBusy(false) }
  }

  return <div className="organization-grid">
    {error && <div className="inline-error" role="alert">{error}</div>}
    {groups.map(entity => <section className="organization-card" key={entity}>
      <div className="section-kicker">ORGANIZE YOUR LIBRARY</div><h2>{labels[entity]}</h2>
      <p>{entity === 'projects' ? 'Connect memories from different sources around one line of work.' : entity === 'collections' ? 'Keep hand-picked sets of memories together.' : 'Add quick labels you can use across projects.'}</p>
      <div className="organization-create"><input aria-label={`New ${entity.slice(0, -1)} name`} placeholder={`New ${entity.slice(0, -1)}...`} value={drafts[entity]} maxLength={entity === 'tags' ? 80 : 120} onChange={event => setDrafts(value => ({ ...value, [entity]: event.target.value }))} onKeyDown={event => { if (event.key === 'Enter') void create(entity) }} /><button className="secondary-button" disabled={busy || !drafts[entity].trim()} onClick={() => void create(entity)}><Plus size={15} /> Add</button></div>
      <div className="organization-items">{data[entity].length ? data[entity].map(item => <div className="organization-item" key={item.id}>
        {editing === item.id ? <><input aria-label={`Rename ${item.name}`} autoFocus value={editName} onChange={event => setEditName(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void rename(entity, item.id); if (event.key === 'Escape') setEditing(null) }} /><button aria-label="Save name" disabled={busy} onClick={() => void rename(entity, item.id)}><Check size={15} /></button><button aria-label="Cancel rename" onClick={() => setEditing(null)}><X size={15} /></button></> : <><button className="organization-open" onClick={() => onScope(entity, item.id)}><span>{item.name}</span><small>{item.memory_count ?? 0} memories</small><ArrowRight size={15} /></button><button aria-label={`Rename ${item.name}`} onClick={() => { setEditing(item.id); setEditName(item.name) }}>Rename</button><button aria-label={`Delete ${item.name}`} disabled={busy} onClick={() => void remove(entity, item)}><Trash2 size={15} /></button></>}
      </div>) : <div className="organization-empty">Nothing here yet. Create one above.</div>}</div>
    </section>)}
  </div>
}

export function OrganizationPicker({ memoryId, selected, data, onChanged }: {
  memoryId: string; selected?: Organization; data: Organization;
  onChanged: (value: Organization) => void
}) {
  const [current, setCurrent] = useState<Organization>(selected ?? emptyOrganization)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { setCurrent(selected ?? emptyOrganization) }, [memoryId, selected])

  async function toggle(entity: OrgEntity, item: OrgItem) {
    const next = { ...current, [entity]: current[entity].some(value => value.id === item.id)
      ? current[entity].filter(value => value.id !== item.id) : [...current[entity], item] }
    setBusy(true); setError('')
    try {
      const updated = await api<Organization>(`/organization/memories/${memoryId}`, {
        method: 'PUT', body: JSON.stringify({ project_ids: next.projects.map(value => value.id),
          collection_ids: next.collections.map(value => value.id), tag_ids: next.tags.map(value => value.id) }),
      })
      setCurrent(updated); onChanged(updated)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update organization.') }
    finally { setBusy(false) }
  }

  return <div className="organization-picker"><div className="detail-section-title">Organize</div>
    {groups.map(entity => <div className="organization-picker-group" key={entity}><strong>{labels[entity]}</strong>
      {data[entity].length ? <div className="organization-chips">{data[entity].map(item => <button key={item.id} aria-pressed={current[entity].some(value => value.id === item.id)} className={current[entity].some(value => value.id === item.id) ? 'organization-chip selected' : 'organization-chip'} disabled={busy} onClick={() => void toggle(entity, item)}>{item.name}{current[entity].some(value => value.id === item.id) && <Check size={12} />}</button>)}</div> : <span className="organization-picker-empty">Create {entity} in the Projects workspace.</span>}
    </div>)}{error && <div className="form-error" role="alert">{error}</div>}
  </div>
}
