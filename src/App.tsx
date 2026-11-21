import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, Clock3, Command, Compass,
  ExternalLink, FileText, FolderKanban, GitBranch, Link2, Menu,
  Plus, Search, Sparkles, Trash2, X,
} from 'lucide-react'
import { api, type Session } from './api'
import { OrganizationPicker, OrganizationView, emptyOrganization,
  type Organization, type OrgEntity } from './Organization'
import { ConnectionsView, ProjectOverview, TimelineView } from './Exploration'
import { Annotations, MarkedText, type Annotation, type PdfPage } from './Annotations'
import { AISettings, type AIConfig } from './AISettings'
import { AssistPanel } from './AssistPanel'
import { SuggestionPanel } from './SuggestionPanel'

type Kind = 'note' | 'link' | 'snippet'
type MemoryKind = Kind | 'document' | 'web_page' | 'image' | 'pdf'
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
  capture_reason: string | null
  has_screenshot?: boolean
  project_name?: string | null
  original_asset?: { source_filename: string; mime_type: string; byte_size: number } | null
  capture_method?: string
  source_author?: string | null
  source_image_uri?: string | null
  published_at?: string | null
  match_reasons?: string[]
  snippet?: string | null
  page_number?: number | null
  organization?: Organization
}
type StoredMemory = {
  id: string; title: string; kind: MemoryKind; source_uri: string | null;
  user_note: string; captured_at: string; updated_at: string; status: string; capture_reason: string | null;
  has_screenshot?: boolean
  project_name?: string | null
  original_asset?: { source_filename: string; mime_type: string; byte_size: number } | null
  capture_method?: string
  source_author?: string | null
  source_image_uri?: string | null
  published_at?: string | null
  match_reasons?: string[]
  snippet?: string | null
  page_number?: number | null
  organization?: Organization
}
type Draft = { title: string; kind: Kind; source_url: string; note: string; body: string }

const emptyDraft: Draft = { title: '', kind: 'link', source_url: '', note: '', body: '' }

function fromStored(row: StoredMemory): Memory {
  return { id: row.id, title: row.title, kind: row.kind,
    source_url: row.source_uri ?? '', note: row.user_note,
    captured_at: row.captured_at, updated_at: row.updated_at, status: row.status,
    capture_reason: row.capture_reason, has_screenshot: row.has_screenshot,
    project_name: row.project_name, original_asset: row.original_asset,
    capture_method: row.capture_method, source_author: row.source_author,
    source_image_uri: row.source_image_uri, published_at: row.published_at,
    match_reasons: row.match_reasons, snippet: row.snippet, page_number: row.page_number,
    organization: row.organization }
}

function formatDate(value: string) {
  const date = new Date(value)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function domain(url: string) {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return 'Website' }
}

function memoryStatus(item: Memory) {
  if (item.kind === 'document') return item.status === 'ready' ? 'Ready to read' : `Extraction ${item.status}`
  if (item.kind === 'pdf') return item.status === 'ready' ? 'Page text ready' : item.status === 'partial' ? 'Some pages have no text' : `Processing ${item.status}`
  if (item.kind === 'web_page') return item.status === 'ready' ? 'Page text saved' : item.status === 'partial' ? 'URL saved · text unavailable' : `Page ${item.status}`
  if (item.kind === 'image') return item.status === 'ready' ? 'Text searchable' : item.status === 'partial' ? 'No text detected' : item.status === 'failed' ? 'Recognition failed' : 'Recognizing text'
  return item.note || (item.kind === 'snippet' ? 'Ready to read' : 'No note added')
}

type InterpretedClues = { approximate_date?: string | null; source_domain?: string | null; source_type?: string | null }
function SearchResults({ items, alternatives, matchMode, aiStatus, lowConfidence, clues, onOpen }: { items: Memory[]; alternatives: Memory[]; matchMode: string; aiStatus: string; lowConfidence: boolean; clues: InterpretedClues; onOpen: (id: string, page?: number | null) => void }) {
  if (!items.length) return null
  const hints = [clues.approximate_date && `saved around ${clues.approximate_date}`, clues.source_domain && `source ${clues.source_domain}`, clues.source_type && `${clues.source_type} type`].filter(Boolean)
  return <div className="search-results">{hints.length > 0 && <p className="search-guidance">Ranking hints from your words: {hints.join(' · ')}. These do not exclude other results. Image type hints use saved text, not visual matching.</p>}{aiStatus === 'limit_reached' || aiStatus === 'provider_error' ? <p className="search-guidance">Semantic search is unavailable right now. Showing keyword results.</p> : lowConfidence ? <p className="search-guidance">These semantic matches are uncertain. Check the source and try another clue.</p> : matchMode === 'some_words' ? <p className="search-guidance">No result matched every word. Showing partial word matches, ranked by strength.</p> : items.length > 1 && <p className="search-guidance">Ranked by match strength. Use filters to narrow similar results.</p>}{items.map(item => <div className="search-result" key={item.id}><button className="search-result-main" onClick={() => onOpen(item.id, item.page_number)}>
    <span className={`memory-icon ${item.kind}`}>{['link', 'web_page'].includes(item.kind) ? <Link2 size={18} /> : <FileText size={18} />}</span>
    <span className="search-result-copy"><strong>{item.title}</strong><span className="search-result-meta">{item.kind.replace('_', ' ')} · {formatDate(item.captured_at)}{item.page_number ? ` · Page ${item.page_number}` : ''}</span>
      {item.snippet && <span className="search-snippet">{item.snippet}</span>}
      {!!item.match_reasons?.length && <span className="search-reasons">Matched by {item.match_reasons.map(reason => reason === 'source' ? 'source details' : reason === 'content' ? 'saved text' : reason === 'semantic' ? 'semantic similarity to saved text' : reason === 'approximate_date' ? 'approximate saved date' : reason === 'source_hint' ? 'remembered source' : reason === 'type_hint' ? 'remembered file type' : reason).join(', ')}</span>}
      {item.status !== 'ready' && <span className="search-gap">Saved text {item.status === 'pending' || item.status === 'processing' ? 'is still processing' : 'may be incomplete'}.</span>}
    </span><ArrowRight size={16} className="row-arrow" /></button>
    {item.source_url && <a className="search-source" href={item.source_url} target="_blank" rel="noopener noreferrer">Open source <ExternalLink size={13} /></a>}
    {['document', 'pdf', 'image'].includes(item.kind) && <a className="search-source" href={`/v1/uploads/${item.id}/original`}>Open original <ExternalLink size={13} /></a>}
  </div>)}{lowConfidence && alternatives.length > 0 && <aside className="search-alternatives"><h3>Check exact-text matches</h3><p>Semantic similarity is weak for this query. These sources ranked highest by saved words.</p><div>{alternatives.map(item => <button key={item.id} onClick={() => onOpen(item.id, item.page_number)}>{item.title}{item.page_number ? ` · page ${item.page_number}` : ''}<ArrowRight size={14} /></button>)}</div></aside>}</div>
}

function SearchEmpty({ query }: { query: string }) {
  return <div className="search-prompt"><Search size={26} /><h3>No matching memories</h3><p>{query.trim() ? 'Try fewer words or a different phrase. Source text may be unavailable if extraction failed or is still processing.' : 'No memories match these filters yet. Clear a filter or save a new memory.'}</p></div>
}

function App({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  const [items, setItems] = useState<Memory[]>([])
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'library' | 'search' | 'organization' | 'project' | 'timeline' | 'connections' | 'ai_settings'>('library')
  const [aiSettings, setAISettings] = useState<AIConfig | null>(null)
  const [aiStatus, setAIStatus] = useState('disabled')
  const [lowConfidence, setLowConfidence] = useState(false)
  const [alternatives, setAlternatives] = useState<Memory[]>([])
  const [interpretedClues, setInterpretedClues] = useState<InterpretedClues>({})
  const [activeProjectId, setActiveProjectId] = useState('')
  const [projectRevision, setProjectRevision] = useState(0)
  const [searchDomain, setSearchDomain] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [projectId, setProjectId] = useState('')
  const [tagId, setTagId] = useState('')
  const [collectionId, setCollectionId] = useState('')
  const [organization, setOrganization] = useState<Organization>(emptyOrganization)
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<Sort>('recent')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [matchMode, setMatchMode] = useState('all_words')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [targetPage, setTargetPage] = useState<number | null>(null)
  const [directMemory, setDirectMemory] = useState<Memory | null>(null)
  const [pairingOpen, setPairingOpen] = useState(false)
  const [pairingCode, setPairingCode] = useState('')
  const [pairingBusy, setPairingBusy] = useState(false)
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
  const [pdfPages, setPdfPages] = useState<PdfPage[]>([])
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [manualUrlOpen, setManualUrlOpen] = useState(false)
  const [manualUrl, setManualUrl] = useState('')
  const [manualNote, setManualNote] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const requestId = useRef(0)
  const fileRef = useRef<HTMLInputElement>(null)
  const imageRef = useRef<HTMLInputElement>(null)
  const pdfRef = useRef<HTMLInputElement>(null)
  const docxRef = useRef<HTMLInputElement>(null)
  const importRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async (
    q = query, kind = filter, pageNumber = page, order = sort, silent = false,
  ) => {
    const currentRequest = ++requestId.current
    if (!silent) { setLoading(true); setError('') }
    try {
      if (view !== 'library' && view !== 'search') {
        setItems([]); setTotal(0); setLoading(false); return
      }
      const params = new URLSearchParams({ q, kind,
        limit: String(PAGE_SIZE), offset: String(pageNumber * PAGE_SIZE) })
      if (view === 'library') params.set('sort', order)
      if (view === 'search') {
        if (searchDomain.trim()) params.set('domain', searchDomain.trim())
        if (dateFrom) params.set('date_from', dateFrom)
        if (dateTo) params.set('date_to', dateTo)
        if (projectId) params.set('project_id', projectId)
        if (tagId) params.set('tag_id', tagId)
        if (collectionId) params.set('collection_id', collectionId)
      }
      const endpoint = view === 'search' ? aiSettings?.enabled ? 'ai/search' : 'search' : 'memories'
      const result = await api<{ items: StoredMemory[]; total: number; match_mode?: string; ai_status?: string; low_confidence?: boolean; alternative_items?: StoredMemory[]; interpreted_clues?: InterpretedClues }>(`/${endpoint}?${params}`)
      if (currentRequest === requestId.current) { setItems(result.items.map(fromStored)); setTotal(result.total); setMatchMode(result.match_mode ?? 'all_words'); setAIStatus(result.ai_status ?? 'disabled'); setLowConfidence(result.low_confidence ?? false); setAlternatives((result.alternative_items ?? []).map(fromStored)); setInterpretedClues(result.interpreted_clues ?? {}) }
    } catch (cause) {
      if (!silent && currentRequest === requestId.current) setError(cause instanceof Error ? cause.message : 'Could not load memories.')
    } finally {
      if (!silent && currentRequest === requestId.current) setLoading(false)
    }
  }, [query, filter, page, sort, view, searchDomain, dateFrom, dateTo, projectId, tagId, collectionId, aiSettings?.enabled])

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(query, filter, page, sort) }, 180)
    return () => window.clearTimeout(timer)
  }, [query, filter, page, sort, view, searchDomain, dateFrom, dateTo, projectId, tagId, collectionId, load])

  const refreshOrganization = useCallback(async () => {
    const result = await api<Organization>('/organization')
    setOrganization(result)
  }, [])
  useEffect(() => { void refreshOrganization().catch(() => setError('Could not load projects, tags, and collections.')) }, [refreshOrganization, view])
  useEffect(() => { void api<AIConfig>('/ai/settings').then(setAISettings).catch(() => setAISettings(null)) }, [])

  function openScope(entity: OrgEntity, id: string) {
    if (entity === 'projects') { setActiveProjectId(id); setView('project'); setSelectedId(null); return }
    setProjectId('')
    setTagId(entity === 'tags' ? id : '')
    setCollectionId(entity === 'collections' ? id : '')
    setQuery(''); setFilter('all'); setPage(0); setView('search')
    window.requestAnimationFrame(() => searchRef.current?.focus())
  }

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('memory')
    if (id && /^[0-9a-f-]{36}$/i.test(id)) setSelectedId(id)
  }, [])

  const selectedListStatus = items.find(item => item.id === selectedId)?.status
  useEffect(() => {
    if (!selectedId) return
    let active = true
    api<StoredMemory>(`/memories/${selectedId}`).then(row => {
      if (active) setDirectMemory(fromStored(row))
    }).catch(() => { if (active) { setSelectedId(null); setDirectMemory(null); setError('This memory is no longer available. Refresh the results to continue.'); void load(query, filter, page, sort, true) } })
    return () => { active = false }
  }, [selectedId, selectedListStatus])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setView('search')
        window.requestAnimationFrame(() => searchRef.current?.focus())
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

  const selected = (directMemory?.id === selectedId ? directMemory : null) ??
    items.find(item => item.id === selectedId) ?? null

  useEffect(() => { setAnnotations([]) }, [selected?.id])

  useEffect(() => {
    if (!selected || !['document', 'web_page', 'snippet', 'pdf', 'image'].includes(selected.kind)) {
      setExtracted(null)
      return
    }
    setExtracted(null)
    let active = true
    api<{ body: string }>(`/memories/${selected.id}/content`).then(value => {
      if (active) setExtracted(value.body)
    }).catch(() => { if (active) setExtracted(null) })
    return () => { active = false }
  }, [selected?.id, selected?.kind, selected?.status])

  useEffect(() => {
    if (selected?.kind !== 'pdf') { setPdfPages([]); return }
    let active = true
    api<{ items: PdfPage[] }>(`/memories/${selected.id}/passages`)
      .then(value => { if (active) setPdfPages(value.items) })
      .catch(() => { if (active) setPdfPages([]) })
    return () => { active = false }
  }, [selected?.id, selected?.kind, selected?.status])

  useEffect(() => {
    if (!selectedId || !targetPage || !pdfPages.length) return
    window.requestAnimationFrame(() => document.getElementById(`pdf-page-${targetPage}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
  }, [selectedId, targetPage, pdfPages])

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

  async function openEdit(item: Memory) {
    if (item.kind === 'document' || item.kind === 'web_page' || item.kind === 'image' || item.kind === 'pdf') return
    let body = ''
    if (item.kind === 'snippet') {
      try { body = (await api<{ body: string }>(`/memories/${item.id}/content`)).body }
      catch { setError('Could not load the pasted text for editing.'); return }
    }
    setDraft({ title: item.title, kind: item.kind, source_url: item.source_url, note: item.note,
      body })
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

  async function uploadImage(file: File | undefined) {
    if (!file) return
    if (!/\.(png|jpe?g|webp)$/i.test(file.name)) { setError('Choose a PNG, JPEG, or WebP image.'); return }
    if (file.size > 20 * 1024 * 1024) { setError('Image exceeds the 20 MiB limit.'); return }
    setUploading(true)
    setError('')
    try {
      await api(`/uploads/image?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
      })
      setToast('Image saved to your library')
      setPage(0)
      await load(query, filter, 0, sort)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not upload image.')
    } finally {
      setUploading(false)
      if (imageRef.current) imageRef.current.value = ''
    }
  }

  async function uploadPdf(file: File | undefined) {
    if (!file) return
    if (!/\.pdf$/i.test(file.name)) { setError('Choose a PDF file.'); return }
    if (file.size > 50 * 1024 * 1024) { setError('PDF exceeds the 50 MiB limit.'); return }
    setUploading(true)
    setError('')
    try {
      await api(`/uploads/pdf?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file,
      })
      setToast('PDF saved. Extracting text...')
      setPage(0)
      await load(query, filter, 0, sort)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not upload PDF.')
    } finally {
      setUploading(false)
      if (pdfRef.current) pdfRef.current.value = ''
    }
  }

  async function uploadDocx(file: File | undefined) {
    if (!file) return
    if (!/\.docx$/i.test(file.name)) { setError('Choose a DOCX file.'); return }
    if (file.size > 25 * 1024 * 1024) { setError('DOCX exceeds the 25 MiB limit.'); return }
    setUploading(true)
    setError('')
    try {
      await api(`/uploads/docx?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }, body: file,
      })
      setToast('DOCX saved. Extracting text...')
      setPage(0)
      await load(query, filter, 0, sort)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not upload DOCX.')
    } finally {
      setUploading(false)
      if (docxRef.current) docxRef.current.value = ''
    }
  }

  async function reprocess(item: Memory) {
    setError('')
    try {
      await api(`/memories/${item.id}/reprocess`, { method: 'POST' })
      setToast(item.kind === 'web_page' ? 'Page refresh queued' : 'Extraction queued from the saved original')
      setDirectMemory({ ...item, status: 'pending' })
      await load(query, filter, page, sort, true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not queue extraction.')
    }
  }

  async function saveManualUrl() {
    setSaving(true)
    setEditorError('')
    try {
      await api('/urls', { method: 'POST', body: JSON.stringify({ source_url: manualUrl, user_note: manualNote }) })
      setManualUrlOpen(false)
      setManualUrl('')
      setManualNote('')
      setToast('Page saved. Fetching readable text...')
      setPage(0)
      await load(query, filter, 0, sort)
    } catch (cause) {
      setEditorError(cause instanceof Error ? cause.message : 'Could not save this URL.')
    } finally {
      setSaving(false)
    }
  }

  async function importFile(file: File | undefined) {
    if (!file) return
    const format = /\.zip$/i.test(file.name) ? 'contextos' : /\.html?$/i.test(file.name) ? 'bookmarks' : null
    if (!format) { setError('Choose a Context OS ZIP export or browser bookmarks HTML file.'); return }
    if (file.size > 60 * 1024 * 1024) { setError('Import exceeds the 60 MiB limit.'); return }
    setImporting(true)
    setError('')
    try {
      const result = await api<{ imported: number; duplicates: number; failed: number; items: { index: number; status: string; reason?: string }[] }>(`/import?format=${format}`, {
        method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
      })
      setToast(`Imported ${result.imported} · ${result.duplicates} duplicates · ${result.failed} failed`)
      setPage(0)
      await load(query, filter, 0, sort)
      void refreshOrganization().catch(() => setError('Import finished, but organization could not refresh.'))
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
          user_note: draft.note, ...(draft.kind === 'snippet' ? { body: draft.body } : {}),
        }) })
        setToast('Memory updated')
      } else {
        await api<StoredMemory>('/memories', { method: 'POST', body: JSON.stringify({
          kind: draft.kind, title: draft.title,
          source_uri: draft.kind === 'link' ? draft.source_url : null, user_note: draft.note,
          ...(draft.kind === 'snippet' ? { body: draft.body } : {}),
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
      void refreshOrganization().catch(() => setError('Memory deleted, but organization could not refresh.'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete memory.')
    }
  }

  async function createPairing() {
    setPairingBusy(true)
    setError('')
    try {
      const value = await api<{ code: string }>('/extension/pairings', { method: 'POST' })
      setPairingCode(value.code)
      setPairingOpen(true)
      setMobileNav(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create pairing code.') }
    finally { setPairingBusy(false) }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="brand"><span className="brand-mark"><span /></span><span>context<span className="brand-os">OS</span></span></div>
        <div className="sidebar-scroll">
          <div className="workspace-pill"><span className="workspace-avatar">C</span><span className="workspace-name">My workspace</span><ChevronDown size={14} /></div>
          <div className="nav-label">WORKSPACE</div>
          <button className={view === 'library' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('library'); setQuery(''); setPage(0); setSelectedId(null); setMobileNav(false) }}><Compass size={18} /> Library</button>
          <button className={view === 'search' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('search'); setPage(0); setSelectedId(null); setMobileNav(false); window.requestAnimationFrame(() => searchRef.current?.focus()) }}><Search size={18} /> Search <span className="nav-shortcut">⌘ K</span></button>
          <div className="nav-label nav-label-spaced">EXPLORE</div>
          <button className={view === 'organization' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('organization'); setSelectedId(null); setMobileNav(false) }}><FolderKanban size={18} /> Projects & organization</button>
          <button className={view === 'timeline' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('timeline'); setSelectedId(null); setMobileNav(false) }}><Clock3 size={18} /> Timeline</button>
          <button className={view === 'connections' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('connections'); setSelectedId(null); setMobileNav(false) }}><GitBranch size={18} /> Connections</button>
          <button className={view === 'ai_settings' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('ai_settings'); setSelectedId(null); setMobileNav(false) }}><Sparkles size={18} /> Intelligent Memory</button>
          <div className="sidebar-divider" />
          <div className="nav-label">QUICK CAPTURE</div>
          <button className="nav-item" onClick={() => { openNew('link'); setMobileNav(false) }}><Link2 size={18} /> Save a link <Plus size={15} className="nav-end" /></button>
          <button className="nav-item" onClick={() => { setEditorError(''); setManualUrlOpen(true); setMobileNav(false) }}><Link2 size={18} /> Save webpage <Plus size={15} className="nav-end" /></button>
          <button className="nav-item" onClick={() => { openNew('note'); setMobileNav(false) }}><FileText size={18} /> Write a note <Plus size={15} className="nav-end" /></button>
          <button className="nav-item" onClick={() => { openNew('snippet'); setMobileNav(false) }}><FileText size={18} /> Save pasted text <Plus size={15} className="nav-end" /></button>
          <button className="nav-item" disabled={uploading} onClick={() => { fileRef.current?.click(); setMobileNav(false) }}><FileText size={18} /> {uploading ? 'Uploading...' : 'Upload text file'} <Plus size={15} className="nav-end" /></button>
          <input ref={fileRef} type="file" accept=".txt,.md,text/plain,text/markdown" hidden onChange={event => { void upload(event.target.files?.[0]) }} />
          <button className="nav-item" disabled={uploading} onClick={() => { imageRef.current?.click(); setMobileNav(false) }}><FileText size={18} /> Upload image <Plus size={15} className="nav-end" /></button>
          <input ref={imageRef} type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" hidden onChange={event => { void uploadImage(event.target.files?.[0]) }} />
          <button className="nav-item" disabled={uploading} onClick={() => { pdfRef.current?.click(); setMobileNav(false) }}><FileText size={18} /> Upload PDF <Plus size={15} className="nav-end" /></button>
          <input ref={pdfRef} type="file" accept=".pdf,application/pdf" hidden onChange={event => { void uploadPdf(event.target.files?.[0]) }} />
          <button className="nav-item" disabled={uploading} onClick={() => { docxRef.current?.click(); setMobileNav(false) }}><FileText size={18} /> Upload DOCX <Plus size={15} className="nav-end" /></button>
          <input ref={docxRef} type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden onChange={event => { void uploadDocx(event.target.files?.[0]) }} />
          <button className="nav-item" disabled={pairingBusy} onClick={() => void createPairing()}><Link2 size={18} /> {pairingBusy ? 'Creating code...' : 'Connect extension'} <ArrowRight size={15} className="nav-end" /></button>
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
          <div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMobileNav(true)}><Menu size={20} /></button><span className="breadcrumb-muted">Workspace</span><span className="breadcrumb-separator">/</span><span className="breadcrumb-current">{view === 'search' ? 'Search' : view === 'organization' || view === 'project' ? 'Projects' : view === 'timeline' ? 'Timeline' : view === 'connections' ? 'Connections' : view === 'ai_settings' ? 'Intelligent Memory' : 'Library'}</span></div>
          <div className="topbar-right"><span className="topbar-caption">{session.email}</span><button className="signout-button" onClick={onSignOut}>Sign out</button><div className="top-avatar">{session.email[0]?.toUpperCase()}</div></div>
        </header>

        <main className="page">
          <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot" /> YOUR KNOWLEDGE, IN ONE PLACE</div><h1>{view === 'search' ? <>Find what matters<br /><em>again.</em></> : view === 'organization' || view === 'project' ? <>Keep ideas<br /><em>connected.</em></> : view === 'timeline' ? <>See how ideas<br /><em>unfold.</em></> : view === 'connections' ? <>Follow the<br /><em>connections.</em></> : view === 'ai_settings' ? <>Your memory,<br /><em>your choice.</em></> : <>Good things are worth<br /><em>remembering.</em></>}</h1><p className="page-intro">{view === 'search' ? 'Search titles, notes, sources, and saved text.' : view === 'organization' || view === 'project' ? 'Projects, collections, and tags give your memories a home.' : view === 'timeline' ? 'Explore what you saved and when.' : view === 'connections' ? 'Make the relationships between memories visible.' : view === 'ai_settings' ? 'Choose whether to use cloud intelligence with your private memories.' : 'Everything you save, ready when you need it.'}</p></div><button className="primary-button heading-save" onClick={() => openNew('link')}><Plus size={17} /> New memory</button></div>

          {view === 'organization' ? <OrganizationView data={organization} refresh={refreshOrganization} onScope={openScope} /> :
          view === 'project' ? <><ProjectOverview projectId={activeProjectId} refreshKey={projectRevision} organization={organization} onOpen={setSelectedId} onSearch={() => { setProjectId(activeProjectId); setTagId(''); setCollectionId(''); setQuery(''); setFilter('all'); setPage(0); setView('search') }} />{aiSettings?.enabled && <><SuggestionPanel projectId={activeProjectId} onOpen={(id, page) => { setTargetPage(page ?? null); setSelectedId(id) }} onChanged={() => { setProjectRevision(value => value + 1); void refreshOrganization() }} /><AssistPanel projectId={activeProjectId} onOpen={(id, page) => { setTargetPage(page ?? null); setSelectedId(id) }} /></>}</> :
          view === 'timeline' ? <TimelineView organization={organization} onOpen={setSelectedId} /> :
          view === 'connections' ? <ConnectionsView organization={organization} onOpen={setSelectedId} /> :
          view === 'ai_settings' ? <AISettings settings={aiSettings} onChanged={setAISettings} /> :
          <div className="content-panel">
          <div className="content-header"><div><div className="section-kicker">{view === 'search' ? 'FIND A MEMORY' : 'YOUR COLLECTION'}</div><h2>{view === 'search' ? 'Search results' : 'All memories'} <span className="item-total">{total}</span></h2></div><button className="text-action" onClick={() => openNew('link')}>Add something <ArrowRight size={16} /></button></div>
            <div className="toolbar"><div className="search-box"><Search size={19} /><input ref={searchRef} aria-label="Search memories" placeholder="Search anything you remember..." value={query} onChange={event => { setQuery(event.target.value); setPage(0) }} /><span className="keycap"><Command size={12} /> K</span></div><div className="filters" role="group" aria-label="Memory type"><button className={filter === 'all' ? 'filter active' : 'filter'} onClick={() => { setFilter('all'); setPage(0) }}>All</button><button className={filter === 'web_page' ? 'filter active' : 'filter'} onClick={() => { setFilter('web_page'); setPage(0) }}>Web pages</button><button className={filter === 'link' ? 'filter active' : 'filter'} onClick={() => { setFilter('link'); setPage(0) }}>Links</button><button className={filter === 'note' ? 'filter active' : 'filter'} onClick={() => { setFilter('note'); setPage(0) }}>Notes</button><button className={filter === 'snippet' ? 'filter active' : 'filter'} onClick={() => { setFilter('snippet'); setPage(0) }}>Pasted text</button><button className={filter === 'image' ? 'filter active' : 'filter'} onClick={() => { setFilter('image'); setPage(0) }}>Images</button><button className={filter === 'pdf' ? 'filter active' : 'filter'} onClick={() => { setFilter('pdf'); setPage(0) }}>PDFs</button><button className={filter === 'document' ? 'filter active' : 'filter'} onClick={() => { setFilter('document'); setPage(0) }}>Files</button></div>{view === 'library' && <select className="sort-select" aria-label="Sort memories" value={sort} onChange={event => { setSort(event.target.value as Sort); setPage(0) }}><option value="recent">Newest</option><option value="updated">Updated</option><option value="title">Title</option></select>}</div>

            {view === 'search' && <div className="search-filters">
              <label>Source domain<input aria-label="Source domain" placeholder="example.com" value={searchDomain} onChange={event => { setSearchDomain(event.target.value); setPage(0) }} /></label>
              <label>From<input aria-label="Captured from date" type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value); setPage(0) }} /></label>
              <label>To<input aria-label="Captured through date" type="date" value={dateTo} onChange={event => { setDateTo(event.target.value); setPage(0) }} /></label>
              <label>Project<select aria-label="Project filter" value={projectId} onChange={event => { setProjectId(event.target.value); setPage(0) }}><option value="">Any project</option>{organization.projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Tag<select aria-label="Tag filter" value={tagId} onChange={event => { setTagId(event.target.value); setPage(0) }}><option value="">Any tag</option>{organization.tags.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Collection<select aria-label="Collection filter" value={collectionId} onChange={event => { setCollectionId(event.target.value); setPage(0) }}><option value="">Any collection</option>{organization.collections.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              {(searchDomain || dateFrom || dateTo || projectId || tagId || collectionId) && <button className="text-action" onClick={() => { setSearchDomain(''); setDateFrom(''); setDateTo(''); setProjectId(''); setTagId(''); setCollectionId(''); setPage(0) }}>Clear filters</button>}
            </div>}
            {error && <div className="inline-error" role="alert">{error}<button onClick={() => void load()}>Try again</button></div>}
            {loading ? <div className="loading-state"><div className="spinner" /> Gathering your memories...</div> : view === 'search' && !query.trim() && !projectId && !tagId && !collectionId && !searchDomain && !dateFrom && !dateTo ? <div className="search-prompt"><Search size={26} /><h3>What are you looking for?</h3><p>Search a title, a phrase from saved text, or a source you remember.</p></div> : view === 'search' && items.length ? <SearchResults items={items} alternatives={alternatives} clues={interpretedClues} matchMode={matchMode} aiStatus={aiStatus} lowConfidence={lowConfidence} onOpen={(id, page) => { setTargetPage(page ?? null); setSelectedId(id) }} /> : view === 'search' ? <SearchEmpty query={query} /> : items.length ? <div className="memory-list">{items.map(item => <button className="memory-row" key={item.id} onClick={() => setSelectedId(item.id)}><span className={`memory-icon ${item.kind}`}>{['link', 'web_page'].includes(item.kind) ? <Link2 size={18} /> : <FileText size={18} />}</span><span className="memory-copy"><span className="memory-title">{item.title}</span><span className="memory-subline">{['link', 'web_page'].includes(item.kind) ? domain(item.source_url) : item.kind === 'document' ? 'Document' : item.kind === 'pdf' ? 'PDF' : item.kind === 'image' ? 'Image' : item.kind === 'snippet' ? 'Pasted text' : 'Personal note'}<span className="subline-dot">·</span>{memoryStatus(item)}</span></span><span className="memory-date">{formatDate(item.captured_at)}</span><ArrowRight size={16} className="row-arrow" /></button>)}</div> : <div className="empty-state"><div className="empty-art" aria-hidden="true"><div className="art-circle art-circle-one" /><div className="art-circle art-circle-two" /><div className="art-card art-card-back"><span /><span /></div><div className="art-card art-card-front"><BookOpen size={24} /><span /><span /></div><div className="art-sparkle"><Sparkles size={18} /></div></div><h3>{query ? 'Nothing matched that memory' : 'Your memory starts here'}</h3><p>{query ? 'Try a different phrase or change the filter.' : 'Save a useful link, note, or pasted passage. We’ll make it easy to find again.'}</p>{!query && <div className="empty-actions"><button className="primary-button" onClick={() => openNew('link')}><Link2 size={16} /> Save a link</button><button className="secondary-button" onClick={() => { setEditorError(''); setManualUrlOpen(true) }}><Link2 size={16} /> Save webpage</button><button className="secondary-button" onClick={() => openNew('note')}><FileText size={16} /> Write a note</button><button className="secondary-button" onClick={() => openNew('snippet')}><FileText size={16} /> Paste text</button><button className="secondary-button" onClick={() => pdfRef.current?.click()}><FileText size={16} /> Upload PDF</button><button className="secondary-button" onClick={() => docxRef.current?.click()}><FileText size={16} /> Upload DOCX</button><button className="secondary-button" onClick={() => imageRef.current?.click()}><FileText size={16} /> Upload image</button><button className="secondary-button" onClick={() => fileRef.current?.click()}><FileText size={16} /> Upload text</button></div>}</div>}
            {total > PAGE_SIZE && <div className="pagination"><span>{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}</span><div><button disabled={page === 0} onClick={() => { setPage(page - 1); setSelectedId(null) }}>Previous</button><button disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => { setPage(page + 1); setSelectedId(null) }}>Next</button></div></div>}
          </div>}
          <div className="page-footnote"><Sparkles size={14} /> A place for ideas, references, and everything in between.</div>
        </main>
      </div>

      {selected && <div className="overlay" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedId(null) }}>
        <section className="detail-panel" role="dialog" aria-modal="true" aria-label="Memory details">
          <div className="detail-top"><button className="back-button" onClick={() => setSelectedId(null)}><ArrowLeft size={18} /> {view === 'search' ? 'Back to results' : 'Back to library'}</button><button className="icon-button" aria-label="Close details" onClick={() => setSelectedId(null)}><X size={20} /></button></div>
          <div className="detail-body">
            <div className={`detail-icon ${selected.kind}`}>{['link', 'web_page'].includes(selected.kind) ? <Link2 size={23} /> : <FileText size={23} />}</div>
            <div className="detail-kicker">{selected.kind === 'web_page' ? 'BROWSER CAPTURE' : selected.kind === 'link' ? 'SAVED LINK' : selected.kind === 'document' ? 'TEXT DOCUMENT' : selected.kind === 'pdf' ? 'SAVED PDF' : selected.kind === 'image' ? 'SAVED IMAGE' : selected.kind === 'snippet' ? 'PASTED TEXT' : 'PERSONAL NOTE'} <span>·</span> {formatDate(selected.captured_at)}</div>
            <h2>{selected.title}</h2>
            {selected.source_url && <a className="source-link" href={selected.source_url} target="_blank" rel="noopener noreferrer">{domain(selected.source_url)} <ExternalLink size={15} /></a>}
            {['document', 'image', 'pdf'].includes(selected.kind) && <a className="source-link" href={`/v1/uploads/${selected.id}/original`}>Download original <ExternalLink size={15} /></a>}
            {(['document', 'pdf', 'image'].includes(selected.kind) || selected.kind === 'web_page' && selected.capture_method === 'manual') && <button className="source-link" disabled={['pending', 'processing'].includes(selected.status)} onClick={() => void reprocess(selected)}>{selected.kind === 'web_page' ? 'Refresh page text' : 'Reprocess original'} <ArrowRight size={15} /></button>}
            {selected.kind === 'web_page' && selected.has_screenshot && <a className="source-link" href={`/v1/uploads/${selected.id}/screenshot`} target="_blank" rel="noopener noreferrer">View saved screenshot <ExternalLink size={15} /></a>}
            <div className="detail-divider" />
            {selected.kind === 'image' && <><div className="detail-section-title">Preview</div><img className="memory-image-preview" src={`/v1/uploads/${selected.id}/preview`} alt={selected.title} /><div className="detail-section-title">Recognized text</div><p className="detail-note"><MarkedText text={extracted ?? (selected.status === 'pending' || selected.status === 'processing' ? 'Recognizing text...' : selected.status === 'failed' ? 'Text recognition failed. The original is still available.' : 'No text was detected in this image.')} annotations={annotations} kind="content" /></p><div className="detail-divider" /></>}
            {['web_page', 'snippet'].includes(selected.kind) && <><div className="detail-section-title">Your note</div><p className="detail-note"><MarkedText text={selected.note || 'No note added yet.'} annotations={annotations} kind="note" /></p><div className="detail-divider" /></>}
            {selected.kind !== 'image' && <><div className="detail-section-title">{selected.kind === 'document' || selected.kind === 'pdf' ? 'Extracted text' : selected.kind === 'web_page' ? 'Captured page text' : selected.kind === 'snippet' ? 'Pasted text' : 'Your note'}</div>
            {selected.kind === 'pdf' ? <div className="pdf-pages">{pdfPages.length ? pdfPages.map(page => <section id={`pdf-page-${page.page_number}`} key={page.page_number}><strong>Page {page.page_number}</strong><p className="detail-note"><MarkedText text={page.body} annotations={annotations} kind="content" start={page.start_offset} page={page.page_number} /></p></section>) : <p className="detail-note">{selected.status === 'partial' ? 'No text was detected on this PDF. The original is still available.' : selected.status === 'failed' ? 'PDF processing failed. The original is still available.' : 'Extracting PDF text...'}</p>}{selected.status === 'failed' && pdfPages.length > 0 && <p className="detail-note">Latest retry failed. Showing previously extracted text.</p>}{selected.status === 'partial' && pdfPages.length > 0 && <p className="detail-note">Some pages have no detectable text.</p>}</div> : <p className="detail-note"><MarkedText text={selected.kind === 'document' ? extracted ?? (selected.status === 'failed' ? 'Text extraction failed. The original file is still available.' : selected.status === 'partial' ? 'No readable text was found in this document.' : 'Extracting text from the original file...') : selected.kind === 'web_page' ? extracted ?? (selected.status === 'pending' || selected.status === 'processing' ? 'Fetching page text...' : selected.capture_method === 'manual' ? `Only the URL was saved (${selected.capture_reason || 'text unavailable'}). You can refresh the page text later.` : `Only the URL and title were saved (${selected.capture_reason || 'text unavailable'}). Try saving the page again from the extension.`) : selected.kind === 'snippet' ? extracted ?? 'Loading pasted text...' : selected.note || 'No note added yet.'} annotations={annotations} kind={selected.kind === 'note' || selected.kind === 'link' ? 'note' : 'content'} /></p>}
            <div className="detail-divider" /></>}
            <div className="detail-section-title">Details</div><div className="detail-meta"><span>Type</span><strong>{selected.kind === 'web_page' ? 'Web page' : selected.kind === 'link' ? 'Link' : selected.kind === 'document' ? 'Document' : selected.kind === 'pdf' ? 'PDF' : selected.kind === 'image' ? 'Image' : selected.kind === 'snippet' ? 'Pasted text' : 'Note'}</strong><span>Saved</span><strong>{formatDate(selected.captured_at)}</strong><span>Updated</span><strong>{formatDate(selected.updated_at)}</strong><span>Status</span><strong>{selected.status}</strong>{selected.capture_reason && <><span>Processing</span><strong>{selected.capture_reason.replaceAll('_', ' ')}</strong></>}{selected.source_author && <><span>Author</span><strong>{selected.source_author}</strong></>}{selected.published_at && <><span>Published</span><strong>{formatDate(selected.published_at)}</strong></>}{selected.source_image_uri && <><span>Page image</span><a href={selected.source_image_uri} target="_blank" rel="noopener noreferrer">View at source</a></>}{selected.kind === 'web_page' && selected.capture_method === 'manual' && <><span>Saved copy</span><strong>{extracted ? 'Extracted text only' : selected.status === 'ready' ? 'Extracted text only' : 'URL only'}</strong></>}{selected.original_asset && <><span>File</span><strong>{selected.original_asset.source_filename}</strong><span>Format</span><strong>{selected.original_asset.mime_type}</strong><span>Size</span><strong>{(selected.original_asset.byte_size / 1024).toFixed(1)} KiB</strong></>}{selected.project_name && <><span>Project</span><strong>{selected.project_name}</strong></>}</div>
            {selected.organization ? <OrganizationPicker memoryId={selected.id} selected={selected.organization} data={organization} onChanged={value => { setDirectMemory(previous => previous?.id === selected.id ? { ...previous, organization: value } : previous); void refreshOrganization() }} /> : <p className="organization-picker-empty">Loading organization...</p>}
            <Annotations key={selected.id} memoryId={selected.id} note={selected.note} content={extracted} pdfPages={pdfPages} onChange={setAnnotations} />
            {aiSettings?.enabled && <><SuggestionPanel memoryId={selected.id} onOpen={(id, page) => { setTargetPage(page ?? null); setSelectedId(id) }} /><AssistPanel memoryIds={[selected.id]} onOpen={(id, page) => { setTargetPage(page ?? null); setSelectedId(id) }} /></>}
            <div className="detail-section-title">Connections</div>
            <ConnectionsView organization={organization} memoryId={selected.id} onOpen={setSelectedId} />
            <div className="detail-actions">{['note', 'link', 'snippet'].includes(selected.kind) && <button className="secondary-button" onClick={() => void openEdit(selected)}>Edit memory</button>}<button className="delete-button" onClick={() => void remove(selected)}><Trash2 size={16} /> Delete</button></div>
          </div>
        </section>
      </div>}

      {pairingOpen && <div className="overlay modal-overlay" onMouseDown={event => { if (event.target === event.currentTarget) setPairingOpen(false) }}><section className="editor-modal" role="dialog" aria-modal="true" aria-label="Connect extension"><div className="modal-header"><div><div className="modal-kicker">BROWSER CAPTURE</div><h2>Connect your extension</h2></div><button className="icon-button" aria-label="Close pairing" onClick={() => setPairingOpen(false)}><X size={20} /></button></div><p className="pairing-help">Load the unpacked extension from <code>extension/dist</code>, click its icon, and paste this one-time code. It expires in 10 minutes.</p><div className="pairing-code">{pairingCode}</div><div className="modal-footer"><button className="secondary-button" onClick={() => { void navigator.clipboard.writeText(pairingCode); setToast('Pairing code copied') }}>Copy code</button><button className="primary-button" onClick={() => setPairingOpen(false)}>Done</button></div></section></div>}

      {manualUrlOpen && <div className="overlay modal-overlay" onMouseDown={event => { if (event.target === event.currentTarget) setManualUrlOpen(false) }}><section className="editor-modal" role="dialog" aria-modal="true" aria-label="Save webpage"><div className="modal-header"><div><div className="modal-kicker">SAVE FROM A URL</div><h2>Save a webpage</h2></div><button className="icon-button" aria-label="Close" onClick={() => setManualUrlOpen(false)}><X size={20} /></button></div><p className="pairing-help">Enter a public webpage URL. We’ll save readable text when the site permits access; otherwise, your URL and note remain available.</p><label className="field-label" htmlFor="manual-url">Page URL</label><input id="manual-url" className="field-input" type="url" placeholder="https://example.com/article" value={manualUrl} onChange={event => setManualUrl(event.target.value)} /><label className="field-label" htmlFor="manual-note">Your note (optional)</label><textarea id="manual-note" className="field-input field-textarea" value={manualNote} onChange={event => setManualNote(event.target.value)} maxLength={20000} />{editorError && <div className="form-error" role="alert">{editorError}</div>}<div className="modal-footer"><button className="secondary-button" onClick={() => setManualUrlOpen(false)}>Cancel</button><button className="primary-button" disabled={saving || !manualUrl.trim()} onClick={() => void saveManualUrl()}>{saving ? 'Saving...' : 'Save webpage'} <ArrowRight size={16} /></button></div></section></div>}

      {editor && <div className="overlay modal-overlay" onMouseDown={event => { if (event.target === event.currentTarget) setEditor(null) }}>
        <section className="editor-modal" role="dialog" aria-modal="true" aria-label={editor === 'new' ? 'New memory' : 'Edit memory'}>
          <div className="modal-header"><div><div className="modal-kicker">{editor === 'new' ? 'CAPTURE SOMETHING' : 'MAKE A CHANGE'}</div><h2>{editor === 'new' ? 'A new memory' : 'Edit memory'}</h2></div><button className="icon-button" aria-label="Close editor" onClick={() => setEditor(null)}><X size={20} /></button></div>
          {editor === 'new' && <div className="type-switch"><button className={draft.kind === 'link' ? 'selected' : ''} onClick={() => setDraft({ ...draft, kind: 'link' })}><Link2 size={17} /> Link</button><button className={draft.kind === 'note' ? 'selected' : ''} onClick={() => setDraft({ ...draft, kind: 'note' })}><FileText size={17} /> Note</button><button className={draft.kind === 'snippet' ? 'selected' : ''} onClick={() => setDraft({ ...draft, kind: 'snippet' })}><FileText size={17} /> Pasted text</button></div>}
          <label className="field-label" htmlFor="memory-title">Title</label><input id="memory-title" className="field-input" autoFocus placeholder={draft.kind === 'link' ? 'What did you find?' : 'Give this a name'} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} maxLength={240} />
          {draft.kind === 'link' && <><label className="field-label" htmlFor="memory-url">URL</label><input id="memory-url" className="field-input" type="url" placeholder="https://example.com/article" value={draft.source_url} onChange={event => setDraft({ ...draft, source_url: event.target.value })} /></>}
          {draft.kind === 'snippet' && <><label className="field-label" htmlFor="memory-body">Pasted text</label><textarea id="memory-body" className="field-input field-textarea" placeholder="Paste text you want to keep..." value={draft.body} onChange={event => setDraft({ ...draft, body: event.target.value })} maxLength={2 * 1024 * 1024} /></>}
          <label className="field-label" htmlFor="memory-note">{draft.kind === 'link' ? 'Why it matters' : draft.kind === 'snippet' ? 'Your note (optional)' : 'Your note'}</label><textarea id="memory-note" className="field-input field-textarea" placeholder={draft.kind === 'link' ? 'Add a little context for your future self...' : draft.kind === 'snippet' ? 'Add context about this text...' : 'Write what you want to remember...'} value={draft.note} onChange={event => setDraft({ ...draft, note: event.target.value })} maxLength={20000} />
          {editorError && <div className="form-error" role="alert">{editorError}</div>}<div className="modal-footer"><button className="secondary-button" onClick={() => setEditor(null)}>Cancel</button><button className="primary-button" disabled={saving} onClick={() => void save()}>{saving ? 'Saving...' : editor === 'new' ? 'Save memory' : 'Save changes'} <ArrowRight size={16} /></button></div>
        </section>
      </div>}
      {toast && <div className="toast" role="status"><Check size={16} /> {toast}</div>}
      {mobileNav && <button className="nav-scrim" aria-label="Close menu" onClick={() => setMobileNav(false)} />}
    </div>
  )
}

export default App
