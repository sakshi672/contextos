import { useState } from 'react'
import { api } from './api'

type Source = { source_id: string; memory_id: string; passage_id: string | null; page_number: number | null; title: string }
type Claim = { text: string; kind: 'fact' | 'inference' | 'missing'; source_ids: string[]; sources: Source[] }
type Answer = { answer: string; claims: Claim[]; cached: boolean }
type Task = 'question' | 'summary' | 'comparison' | 'ideas'

export function AssistPanel({ projectId, memoryIds, onOpen }: { projectId?: string; memoryIds?: string[]; onOpen: (id: string, page?: number | null) => void }) {
  const [task, setTask] = useState<Task>(projectId ? 'question' : 'summary')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function run() {
    setBusy(true); setError(''); setAnswer(null)
    try {
      const result = await api<Answer>('/ai/assist', { method: 'POST', body: JSON.stringify({ task, project_id: projectId, memory_ids: memoryIds ?? [], question }) })
      setAnswer(result)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not generate an answer.') }
    finally { setBusy(false) }
  }
  return <section className="assist-panel"><div className="section-kicker">INTELLIGENT MEMORY</div><h3>Ask your sources</h3><p>Answers use your saved text. Check cited passages before relying on a claim.</p><div className="assist-controls"><label>Task<select value={task} onChange={event => { setTask(event.target.value as Task); setAnswer(null) }}><option value="question">Question</option><option value="summary">Summary</option>{projectId && <option value="comparison">Compare sources</option>}<option value="ideas">Grounded ideas</option></select></label>{task === 'question' && <label>Question<input value={question} maxLength={500} placeholder="What do these sources tell me?" onChange={event => setQuestion(event.target.value)} /></label>}<button className="primary-button" disabled={busy || (task === 'question' && !question.trim())} onClick={() => void run()}>{busy ? 'Reading sources…' : 'Generate'}</button></div>{error && <p className="inline-error" role="alert">{error}</p>}{answer && <div className="assist-answer"><p>{answer.answer}</p>{answer.claims.map((claim, index) => <div className="assist-claim" key={index}><span className={`assist-kind ${claim.kind}`}>{claim.kind}</span><span>{claim.text}</span>{claim.sources.map(source => <button className="assist-citation" key={source.source_id} onClick={() => onOpen(source.memory_id, source.page_number)}>{source.title}{source.page_number ? ` · p. ${source.page_number}` : ''}</button>)}</div>)}{answer.cached && <small>Reused from unchanged sources</small>}</div>}</section>
}
