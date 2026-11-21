import { useEffect, useState } from 'react'
import { api } from './api'

export type AIConfig = { enabled: boolean; configured: boolean; provider: string; embedding_model: string; answer_model: string; monthly_token_limit: number; used_tokens: number; reserved_tokens: number; disclosure: string }

export function AISettings({ settings, onChanged }: { settings: AIConfig | null; onChanged: (value: AIConfig) => void }) {
  const [limit, setLimit] = useState(100000)
  const [consent, setConsent] = useState(false)
  const [deleteDerived, setDeleteDerived] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (settings?.monthly_token_limit) setLimit(settings.monthly_token_limit) }, [settings?.monthly_token_limit])
  async function update(enabled: boolean) {
    setBusy(true); setError('')
    try { const result = await api<AIConfig>('/ai/settings', { method: 'PUT', body: JSON.stringify({ enabled, monthly_token_limit: enabled ? limit : 0, confirm_cloud_processing: enabled && consent, delete_derived_data: !enabled && deleteDerived }) }); onChanged(result); setConsent(false) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update AI settings.') }
    finally { setBusy(false) }
  }
  return <section className="ai-settings explore-stack"><div className="explore-project-head"><div><div className="section-kicker">YOUR CHOICE</div><h2>Intelligent Memory</h2><p>Cloud AI is off by default. Your library, search, projects, timeline, and manual connections work without it.</p></div><span className="phase-chip">{settings?.enabled ? 'On' : 'Off'}</span></div>{settings && <div className="explore-create"><h3>Cloud processing</h3><p>{settings.disclosure}</p><p>Provider: OpenAI · Embeddings: {settings.embedding_model} · Answers: {settings.answer_model}. The server operator supplies the API key. Provider pricing and retention details are in the developer notes.</p><p>Usage this month: {settings.used_tokens.toLocaleString()} tokens. Monthly hard limit: {settings.monthly_token_limit.toLocaleString()} tokens. Limits are measured in tokens, not a guaranteed currency amount.</p>{!settings.configured && <div className="inline-error">Cloud AI is not configured on this server yet. The rest of Context OS remains available.</div>}<div className="explore-form"><label>Monthly token limit<input type="number" min="1" max="10000000" value={limit} onChange={e => setLimit(Number(e.target.value))} /></label>{!settings.enabled && <label className="ai-checkbox"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> I agree to send my saved text and questions to the configured provider for these features.</label>}{settings.enabled && <label className="ai-checkbox"><input type="checkbox" checked={deleteDerived} onChange={e => setDeleteDerived(e.target.checked)} /> Delete my generated embeddings, suggestions, and answers when disabling.</label>}{error && <div className="inline-error" role="alert">{error}</div>}{settings.enabled ? <div className="explore-two"><button className="secondary-button" disabled={busy} onClick={() => void update(true)}>Update limit</button><button className="delete-button" disabled={busy} onClick={() => void update(false)}>Disable AI</button></div> : <button className="primary-button" disabled={busy || !consent || !settings.configured || limit < 1} onClick={() => void update(true)}>Enable Intelligent Memory</button>}</div></div>}</section>
}
