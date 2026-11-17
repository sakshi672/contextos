import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, Clock3, Command, Compass,
  ExternalLink, FileText, FolderKanban, GitBranch, Link2, Menu,
  Plus, Search, Sparkles, Trash2, X,
} from 'lucide-react'
import { api, type Session } from './api'

type Kind = 'note' | 'link'
type MemoryKind = Kind | 'document'
type Filter = 'all' | MemoryKind
type Sort = 'recent' | 'updated' | 'title'
const PAGE_SIZE = 20
type Memory = {
  id: string
  title: string
  kind: MemoryKind
  source_url: string
  note: string
  captured_at: string
  updated_at: string
  status: string
}
type StoredMemory = {
  id: string; title: string; kind: MemoryKind; source_uri: string | null;
  user_note: string; captured_at: string; updated_at: string; status: string
}
type Draft = { title: string; kind: Kind; source_url: string; note: string }

const emptyDraft: Draft = { title: '', kind: 'link', source_url: '', note: '' }

function fromStored(row: StoredMemory): Memory {
  return { id: row.id, title: row.title, kind: row.kind,
    source_url: row.source_uri ?? '', note: row.user_note,
    captured_at: row.captured_at, updated_at: row.updated_at, status: row.status }
}

function formatDate(value: string) {
  const date = new Date(value)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function domain(url: string) {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return 'Website' }
}

function App({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  const [items, setItems] = useState<Memory[]>([])
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<Sort>('recent')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editor, setEditor] = useState<'new' | 'edit' | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [editorError, setEditorError] = useState('')
  const [toast, setToast] = useState('')
  const [mobileNav, setMobileNav] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [extracted, setExtracted] = useState<string | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const importRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async (
    q = query, kind = filter, pageNumber = page, order = sort, silent = false,
  ) => {
    if (!silent) { setLoading(true); setError('') }
    try {
      const params = new URLSearchParams({ q, kind, sort: order,
        limit: String(PAGE_SIZE), offset: String(pageNumber * PAGE_SIZE) })
      const result = await api<{ items: StoredMemory[]; total: number }>(`/memories?${params}`)
      setItems(result.items.map(fromStored))
      setTotal(result.total)
    } catch (cause) {
      if (!silent) setError(cause instanceof Error ? cause.message : 'Could not load memories.')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [query, filter, page, sort])

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(query, filter, page, sort) }, 180)
    return () => window.clearTimeout(timer)
  }, [query, filter, page, sort, load])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchRef.current?.focus()
      }
      if (event.key === 'Escape') { setEditor(null); setSelectedId(null); setMobileNav(false) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 3400)
    return () => window.clearTimeout(timer)
  }, [toast])

  const selected = items.find(item => item.id === selectedId) ?? null

  useEffect(() => {
    if (!selected || selected.kind !== 'document' || selected.status !== 'ready') {
      setExtracted(null)
      return
    }
    let active = true
    api<{ body: string }>(`/memories/${selected.id}/content`).then(value => {
      if (active) setExtracted(value.body)
    }).catch(() => { if (active) setExtracted(null) })
    return () => { active = false }
  }, [selected?.id, selected?.kind, selected?.status])

  useEffect(() => {
    if (!items.some(item => item.status === 'pending' || item.status === 'processing')) return
    const timer = window.setInterval(() => { void load(query, filter, page, sort, true) }, 3000)
    return () => window.clearInterval(timer)
  }, [items, load, query, filter, page, sort])

  function openNew(kind: Kind = 'link') {
    setDraft({ ...emptyDraft, kind })
    setEditorError('')
    setEditor('new')
  }

  function openEdit(item: Memory) {
    if (item.kind === 'document') return
    setDraft({ title: item.title, kind: item.kind, source_url: item.source_url, note: item.note })
    setEditorError('')
    setEditor('edit')
  }

  async function upload(file: File | undefined) {
    if (!file) return
    if (!/\.(txt|md)$/i.test(file.name)) { setError('Choose a UTF-8 TXT or Markdown file.'); return }
    if (file.size > 10 * 1024 * 1024) { setError('File exceeds the 10 MiB limit.'); return }
    setUploading(true)
    setError('')
    try {
      await api(`/uploads/text?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
      })
      setToast('File saved. Extracting text...')
      setPage(0)
      await load(query, filter, 0, sort)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not upload file.')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function importFile(file: File | undefined) {
    if (!file) return
    const format = /\.zip$/i.test(file.name) ? 'contextos' : /\.html?$/i.test(file.name) ? 'bookmarks' : null
    if (!format) { setError('Choose a Context OS ZIP export or browser bookmarks HTML file.'); return }
    if (file.size > 50 * 1024 * 1024) { setError('Import exceeds the 50 MiB limit.'); return }
    setImporting(true)
    setError('')
    try {
      const result = await api<{ imported: number; duplicates: number; failed: number; items: { index: number; status: string; reason?: string }[] }>(`/import?format=${format}`, {
        method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
      })
      setToast(`Imported ${result.imported} · ${result.duplicates} duplicates · ${result.failed} failed`)
      setPage(0)
      await load(query, filter, 0, sort)
      if (result.failed) {
        const firstFailure = result.items.find(item => item.status === 'failed')
        setError(`${result.failed} import item${result.failed === 1 ? '' : 's'} failed. First failure (item ${(firstFailure?.index ?? 0) + 1}): ${firstFailure?.reason ?? 'Unsupported data'}`)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not import file.')
    } finally {
      setImporting(false)
      if (importRef.current) importRef.current.value = ''
    }
  }

  async function save() {
    setSaving(true)
    setEditorError('')
    try {
      if (editor === 'edit' && selected) {
        await api<StoredMemory>(`/memories/${selected.id}`, { method: 'PATCH', body: JSON.stringify({
          kind: draft.kind, title: draft.title, source_uri: draft.kind === 'link' ? draft.source_url : null,
          user_note: draft.note,
        }) })
        setToast('Memory updated')
      } else {
        await api<StoredMemory>('/memories', { method: 'POST', body: JSON.stringify({
          kind: draft.kind, title: draft.title,
          source_uri: draft.kind === 'link' ? draft.source_url : null, user_note: draft.note,
        }) })
        setToast('Saved to your library')
      }
      setEditor(null)
      setSelectedId(null)
      setPage(0)
      await load(query, filter, 0, sort)
    } catch (cause) {
      setEditorError(cause instanceof Error ? cause.message : 'Could not save memory.')
    } finally {
      setSaving(false)
    }
  }

  async function remove(item: Memory) {
    if (!window.confirm(`Delete “${item.title}” permanently?`)) return
    try {
      await api<{ deleted: boolean }>(`/memories/${item.id}`, { method: 'DELETE' })
      setSelectedId(null)
      setToast('Memory deleted')
      const nextPage = page > 0 && items.length === 1 ? page - 1 : page
      if (nextPage !== page) setPage(nextPage)
      await load(query, filter, nextPage, sort)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete memory.')
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="brand"><span className="brand-mark"><span /></span><span>context<span className="brand-os">OS</span></span></div>
        <div className="sidebar-scroll">
          <div className="workspace-pill"><span className="workspace-avatar">C</span><span className="workspace-name">My workspace</span><ChevronDown size={14} /></div>
          <div className="nav-label">WORKSPACE</div>
          <button className="nav-item active" onClick={() => { setSelectedId(null); setMobileNav(false) }}><Compass size={18} /> Library <span className="nav-count">{total}</span></button>
          <button className="nav-item" onClick={() => { searchRef.current?.focus(); setMobileNav(false) }}><Search size={18} /> Search <span className="nav-shortcut">⌘ K</span></button>
          <div className="nav-label nav-label-spaced">EXPLORE</div>
          <button className="nav-item" disabled title="Projects are planned for a later phase"><FolderKanban size={18} /> Projects <span className="soon">Soon</span></button>
          <button className="nav-item" disabled title="Timeline is planned for a later phase"><Clock3 size={18} /> Timeline <span className="soon">Soon</span></button>
          <button className="nav-item" disabled title="Connections are planned for a later phase"><GitBranch size={18} /> Connections <span className="soon">Soon</span></button>
          <div className="sidebar-divider" />
          <div className="nav-label">QUICK CAPTURE</div>
          <button className="nav-item" onClick={() => { openNew('link'); setMobileNav(false) }}><Link2 size={18} /> Save a link <Plus size={15} className="nav-end" /></button>
          <button className="nav-item" onClick={() => { openNew('note'); setMobileNav(false) }}><FileText size={18} /> Write a note <Plus size={15} className="nav-end" /></button>
          <button className="nav-item" disabled={uploading} onClick={() => { fileRef.current?.click(); setMobileNav(false) }}><FileText size={18} /> {uploading ? 'Uploading...' : 'Upload text file'} <Plus size={15} className="nav-end" /></button>
          <input ref={fileRef} type="file" accept=".txt,.md,text/plain,text/markdown" hidden onChange={event => { void upload(event.target.files?.[0]) }} />
          <div className="sidebar-divider" />
          <div className="nav-label">YOUR DATA</div>
          <a className="nav-item" href="/v1/export" download="contextos-export.zip"><BookOpen size={18} /> Export your data <ArrowRight size={15} className="nav-end" /></a>
          <button className="nav-item" disabled={importing} onClick={() => { importRef.current?.click(); setMobileNav(false) }}><BookOpen size={18} /> {importing ? 'Importing...' : 'Import data'} <Plus size={15} className="nav-end" /></button>
          <input ref={importRef} type="file" accept=".zip,.html,.htm,application/zip,text/html" hidden onChange={event => { void importFile(event.target.files?.[0]) }} />
        </div>
        <div className="sidebar-bottom"><div className="phase-chip"><span className="phase-dot" /> Building the foundation</div><div className="sidebar-footer">A quieter way to remember.</div></div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMobileNav(true)}><Menu size={20} /></button><span className="breadcrumb-muted">Workspace</span><span className="breadcrumb-separator">/</span><span className="breadcrumb-current">Library</span></div>
          <div className="topbar-right"><span className="topbar-caption">{session.email}</span><button className="signout-button" onClick={onSignOut}>Sign out</button><div className="top-avatar">{session.email[0]?.toUpperCase()}</div></div>
        </header>

        <main className="page">
          <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot" /> YOUR KNOWLEDGE, IN ONE PLACE</div><h1>Good things are worth<br /><em>remembering.</em></h1><p className="page-intro">Everything you save, ready when you need it.</p></div><button className="primary-button heading-save" onClick={() => openNew('link')}><Plus size={17} /> New memory</button></div>

          <div className="content-panel">
          <div className="content-header"><div><div className="section-kicker">YOUR COLLECTION</div><h2>All memories <span className="item-total">{total}</span></h2></div><button className="text-action" onClick={() => openNew('link')}>Add something <ArrowRight size={16} /></button></div>
            <div className="toolbar"><div className="search-box"><Search size={19} /><input ref={searchRef} aria-label="Search memories" placeholder="Search anything you remember..." value={query} onChange={event => { setQuery(event.target.value); setPage(0) }} /><span className="keycap"><Command size={12} /> K</span></div><div className="filters" role="group" aria-label="Memory type"><button className={filter === 'all' ? 'filter active' : 'filter'} onClick={() => { setFilter('all'); setPage(0) }}>All</button><button className={filter === 'link' ? 'filter active' : 'filter'} onClick={() => { setFilter('link'); setPage(0) }}>Links</button><button className={filter === 'note' ? 'filter active' : 'filter'} onClick={() => { setFilter('note'); setPage(0) }}>Notes</button><button className={filter === 'document' ? 'filter active' : 'filter'} onClick={() => { setFilter('document'); setPage(0) }}>Files</button></div><select className="sort-select" aria-label="Sort memories" value={sort} onChange={event => { setSort(event.target.value as Sort); setPage(0) }}><option value="recent">Newest</option><option value="updated">Updated</option><option value="title">Title</option></select></div>

            {error && <div className="inline-error" role="alert">{error}<button onClick={() => void load()}>Try again</button></div>}
            {loading ? <div className="loading-state"><div className="spinner" /> Gathering your memories...</div> : items.length ? <div className="memory-list">{items.map(item => <button className="memory-row" key={item.id} onClick={() => setSelectedId(item.id)}><span className={`memory-icon ${item.kind}`}>{item.kind === 'link' ? <Link2 size={18} /> : <FileText size={18} />}</span><span className="memory-copy"><span className="memory-title">{item.title}</span><span className="memory-subline">{item.kind === 'link' ? domain(item.source_url) : item.kind === 'document' ? 'Text document' : 'Personal note'}<span className="subline-dot">·</span>{item.kind === 'document' ? item.status === 'ready' ? 'Ready to read' : `Extraction ${item.status}` : item.note || 'No note added'}</span></span><span className="memory-date">{formatDate(item.captured_at)}</span><ArrowRight size={16} className="row-arrow" /></button>)}</div> : <div className="empty-state"><div className="empty-art" aria-hidden="true"><div className="art-circle art-circle-one" /><div className="art-circle art-circle-two" /><div className="art-card art-card-back"><span /><span /></div><div className="art-card art-card-front"><BookOpen size={24} /><span /><span /></div><div className="art-sparkle"><Sparkles size={18} /></div></div><h3>{query ? 'Nothing matched that memory' : 'Your memory starts here'}</h3><p>{query ? 'Try a different phrase or change the filter.' : 'Save a useful link or a thought worth keeping. We’ll make it easy to find again.'}</p>{!query && <div className="empty-actions"><button className="primary-button" onClick={() => openNew('link')}><Link2 size={16} /> Save a link</button><button className="secondary-button" onClick={() => openNew('note')}><FileText size={16} /> Write a note</button><button className="secondary-button" onClick={() => fileRef.current?.click()}><FileText size={16} /> Upload text</button></div>}</div>}
            {total > PAGE_SIZE && <div className="pagination"><span>{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}</span><div><button disabled={page === 0} onClick={() => { setPage(page - 1); setSelectedId(null) }}>Previous</button><button disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => { setPage(page + 1); setSelectedId(null) }}>Next</button></div></div>}
          </div>
          <div className="page-footnote"><Sparkles size={14} /> A place for ideas, references, and everything in between.</div>
        </main>
      </div>

      {selected && <div className="overlay" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedId(null) }}><section className="detail-panel" role="dialog" aria-modal="true" aria-label="Memory details"><div className="detail-top"><button className="back-button" onClick={() => setSelectedId(null)}><ArrowLeft size={18} /> Back to library</button><button className="icon-button" aria-label="Close details" onClick={() => setSelectedId(null)}><X size={20} /></button></div><div className="detail-body"><div className={`detail-icon ${selected.kind}`}>{selected.kind === 'link' ? <Link2 size={23} /> : <FileText size={23} />}</div><div className="detail-kicker">{selected.kind === 'link' ? 'SAVED LINK' : selected.kind === 'document' ? 'TEXT DOCUMENT' : 'PERSONAL NOTE'} <span>·</span> {formatDate(selected.captured_at)}</div><h2>{selected.title}</h2>{selected.source_url && <a className="source-link" href={selected.source_url} target="_blank" rel="noopener noreferrer">{domain(selected.source_url)} <ExternalLink size={15} /></a>}{selected.kind === 'document' && <a className="source-link" href={`/v1/uploads/${selected.id}/original`}>Download original <ExternalLink size={15} /></a>}<div className="detail-divider" /><div className="detail-section-title">{selected.kind === 'document' ? 'Extracted text' : 'Your note'}</div><p className="detail-note">{selected.kind === 'document' ? selected.status === 'ready' ? extracted ?? 'Loading text...' : selected.status === 'failed' ? 'Text extraction failed. The original file is still available.' : 'Extracting text from the original file...' : selected.note || 'No note added yet.'}</p><div className="detail-divider" /><div className="detail-section-title">Details</div><div className="detail-meta"><span>Type</span><strong>{selected.kind === 'link' ? 'Link' : selected.kind === 'document' ? 'Document' : 'Note'}</strong><span>Saved</span><strong>{formatDate(selected.captured_at)}</strong><span>Updated</span><strong>{formatDate(selected.updated_at)}</strong><span>Status</span><strong>{selected.status}</strong></div><div className="detail-actions">{selected.kind !== 'document' && <button className="secondary-button" onClick={() => openEdit(selected)}>Edit memory</button>}<button className="delete-button" onClick={() => void remove(selected)}><Trash2 size={16} /> Delete</button></div></div></section></div>}

      {editor && <div className="overlay modal-overlay" onMouseDown={event => { if (event.target === event.currentTarget) setEditor(null) }}><section className="editor-modal" role="dialog" aria-modal="true" aria-label={editor === 'new' ? 'New memory' : 'Edit memory'}><div className="modal-header"><div><div className="modal-kicker">{editor === 'new' ? 'CAPTURE SOMETHING' : 'MAKE A CHANGE'}</div><h2>{editor === 'new' ? 'A new memory' : 'Edit memory'}</h2></div><button className="icon-button" aria-label="Close editor" onClick={() => setEditor(null)}><X size={20} /></button></div><div className="type-switch"><button className={draft.kind === 'link' ? 'selected' : ''} onClick={() => setDraft({ ...draft, kind: 'link' })}><Link2 size={17} /> Link</button><button className={draft.kind === 'note' ? 'selected' : ''} onClick={() => setDraft({ ...draft, kind: 'note' })}><FileText size={17} /> Note</button></div><label className="field-label" htmlFor="memory-title">Title</label><input id="memory-title" className="field-input" autoFocus placeholder={draft.kind === 'link' ? 'What did you find?' : 'Give this thought a name'} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} maxLength={240} />{draft.kind === 'link' && <><label className="field-label" htmlFor="memory-url">URL</label><input id="memory-url" className="field-input" type="url" placeholder="https://example.com/article" value={draft.source_url} onChange={event => setDraft({ ...draft, source_url: event.target.value })} /></>}<label className="field-label" htmlFor="memory-note">{draft.kind === 'link' ? 'Why it matters' : 'Your note'}</label><textarea id="memory-note" className="field-input field-textarea" placeholder={draft.kind === 'link' ? 'Add a little context for your future self...' : 'Write what you want to remember...'} value={draft.note} onChange={event => setDraft({ ...draft, note: event.target.value })} maxLength={20000} />{editorError && <div className="form-error" role="alert">{editorError}</div>}<div className="modal-footer"><button className="secondary-button" onClick={() => setEditor(null)}>Cancel</button><button className="primary-button" disabled={saving} onClick={() => void save()}>{saving ? 'Saving...' : editor === 'new' ? 'Save memory' : 'Save changes'} <ArrowRight size={16} /></button></div></section></div>}
      {toast && <div className="toast" role="status"><Check size={16} /> {toast}</div>}
      {mobileNav && <button className="nav-scrim" aria-label="Close menu" onClick={() => setMobileNav(false)} />}
    </div>
  )
}

export default App
