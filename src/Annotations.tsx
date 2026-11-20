import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { api } from './api'

export type Annotation = { id: string; location_kind: 'note' | 'content'; quote: string; start_offset: number; end_offset: number; page_number: number | null; note: string; current: boolean }
export type PdfPage = { page_number: number; body: string; start_offset: number; end_offset: number }

export function MarkedText({ text, annotations, kind, start = 0, page }: { text: string; annotations: Annotation[]; kind: 'note' | 'content'; start?: number; page?: number }) {
  const matching = annotations.filter(item => item.current && item.location_kind === kind && (page === undefined || item.page_number === page) && item.start_offset >= start && item.end_offset <= start + text.length).sort((a, b) => a.start_offset - b.start_offset)
  const parts: React.ReactNode[] = []
  let cursor = 0
  for (const item of matching) {
    const begin = item.start_offset - start, end = item.end_offset - start
    if (begin < cursor) continue
    parts.push(text.slice(cursor, begin))
    parts.push(<mark key={item.id} title={item.note || 'Saved highlight'}>{text.slice(begin, end)}</mark>)
    cursor = end
  }
  parts.push(text.slice(cursor))
  return <>{parts}</>
}

export function Annotations({ memoryId, note, content, pdfPages, onChange }: { memoryId: string; note: string; content: string | null; pdfPages: PdfPage[]; onChange: (items: Annotation[]) => void }) {
  const [items, setItems] = useState<Annotation[]>([])
  const [source, setSource] = useState<'note' | 'content'>('note')
  const [page, setPage] = useState('')
  const [quote, setQuote] = useState('')
  const [comment, setComment] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [editNote, setEditNote] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { if (!note && content) setSource('content') }, [note, content])
  useEffect(() => { let live = true; api<{ items: Annotation[] }>(`/memories/${memoryId}/annotations`).then(value => { if (live) { setItems(value.items); onChange(value.items) } }).catch(cause => { if (live) setError(cause.message) }); return () => { live = false } }, [memoryId])
  async function refresh() { const value = await api<{ items: Annotation[] }>(`/memories/${memoryId}/annotations`); setItems(value.items); onChange(value.items) }
  function selection() { const selected = window.getSelection()?.toString().trim(); if (selected) setQuote(selected.slice(0, 2000)) }
  async function create() {
    setError('')
    const selectedPage = pdfPages.find(item => String(item.page_number) === page)
    const body = source === 'note' ? note : selectedPage?.body ?? content ?? ''
    const local = body.indexOf(quote)
    if (local < 0 || !quote) { setError('The quote must appear exactly in the selected text.'); return }
    const offset = source === 'content' && selectedPage ? selectedPage.start_offset : 0
    try {
      await api(`/memories/${memoryId}/annotations`, { method: 'POST', body: JSON.stringify({ location_kind: source, quote, start_offset: offset + local, end_offset: offset + local + quote.length, page_number: source === 'content' && selectedPage ? selectedPage.page_number : null, note: comment }) })
      setQuote(''); setComment(''); await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save highlight.') }
  }
  async function save(id: string) { try { await api(`/annotations/${id}`, { method: 'PATCH', body: JSON.stringify({ note: editNote }) }); setEditing(null); await refresh() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not edit annotation.') } }
  async function remove(id: string) { if (!window.confirm('Remove this highlight?')) return; try { await api(`/annotations/${id}`, { method: 'DELETE' }); await refresh() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not remove annotation.') } }
  return <section className="annotation-section"><div className="detail-section-title">Highlights & annotations</div><p>Select text above, then use “Use selected text,” or enter a short exact quote.</p>{error && <p className="inline-error" role="alert">{error}</p>}<div className="explore-form"><div className="explore-two"><label>Source<select value={source} onChange={e => { setSource(e.target.value as 'note' | 'content'); setPage('') }}><option value="note">Your note</option>{content && <option value="content">Saved text</option>}</select></label>{source === 'content' && pdfPages.length > 0 && <label>PDF page<select value={page} onChange={e => setPage(e.target.value)}><option value="">Select a page</option>{pdfPages.map(item => <option key={item.page_number} value={item.page_number}>Page {item.page_number}</option>)}</select></label>}</div><button className="secondary-button" onClick={selection}>Use selected text</button><label>Exact quote<input value={quote} maxLength={2000} onChange={e => setQuote(e.target.value)} placeholder="Text to highlight" /></label><label>Your annotation<textarea value={comment} maxLength={2000} onChange={e => setComment(e.target.value)} placeholder="Why does this passage matter?" /></label><button className="primary-button" disabled={!quote || (source === 'content' && (!content || (pdfPages.length > 0 && !page)))} onClick={() => void create()}><Plus size={16} /> Save highlight</button></div><div className="annotation-list">{items.map(item => <article key={item.id} className="annotation-card"><div><strong>“{item.quote}”</strong><small>{item.page_number ? `Page ${item.page_number} · ` : ''}{item.location_kind === 'note' ? 'Your note' : 'Saved text'}{!item.current ? ' · Source changed' : ''}</small></div>{editing === item.id ? <div className="explore-form"><textarea value={editNote} maxLength={2000} onChange={e => setEditNote(e.target.value)} /><button className="primary-button" onClick={() => void save(item.id)}>Save note</button></div> : <p>{item.note || 'Highlighted without a note'}</p>}<div className="explore-relation-foot">{item.page_number && <button onClick={() => document.getElementById(`pdf-page-${item.page_number}`)?.scrollIntoView({ behavior: 'smooth' })}>Go to page</button>}<button onClick={() => { setEditing(item.id); setEditNote(item.note) }}>Edit</button><button aria-label="Remove highlight" onClick={() => void remove(item.id)}><Trash2 size={15} /></button></div></article>)}{!items.length && <p className="explore-empty">No highlights yet.</p>}</div></section>
}
