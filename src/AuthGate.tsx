import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, LockKeyhole, Sparkles } from 'lucide-react'
import App from './App'
import { api, setSession, type Session } from './api'

export default function AuthGate() {
  const [session, setCurrent] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api<Session>('/auth/session').then(value => {
      if (active) { setSession(value); setCurrent(value) }
    }).catch(cause => {
      if (active && !(cause instanceof Error && cause.message === 'Sign in required')) {
        setError(cause instanceof Error ? cause.message : 'Could not connect to the API.')
      }
    }).finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const value = await api<Session>(`/auth/${mode}`, {
        method: 'POST', body: JSON.stringify({ email, password }),
      })
      setSession(value)
      setCurrent(value)
      setPassword('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign in.')
    } finally { setBusy(false) }
  }

  async function signOut() {
    try { await api('/auth/logout', { method: 'POST' }) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not sign out.'); return }
    setSession(null)
    setCurrent(null)
  }

  if (checking) return <div className="auth-loading"><span className="spinner" /> Opening your workspace...</div>
  if (session) return <App session={session} onSignOut={() => { void signOut() }} />

  return <div className="auth-shell">
    <div className="auth-brand"><span className="brand-mark"><span /></span><span>context<span className="brand-os">OS</span></span></div>
    <div className="auth-card">
      <div className="auth-icon"><LockKeyhole size={22} /></div>
      <div className="eyebrow"><span className="eyebrow-dot" /> YOUR PRIVATE MEMORY SPACE</div>
      <h1>{mode === 'login' ? 'Welcome back.' : 'Make room for what matters.'}</h1>
      <p>{mode === 'login' ? 'Sign in to find everything you saved.' : 'Create your space to save and recover ideas, links, and more.'}</p>
      <form onSubmit={event => { void submit(event) }}>
        <label className="field-label" htmlFor="auth-email">Email</label>
        <input id="auth-email" className="field-input" type="email" autoComplete="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com" />
        <label className="field-label" htmlFor="auth-password">Password</label>
        <input id="auth-password" className="field-input" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={12} value={password} onChange={event => setPassword(event.target.value)} placeholder="At least 12 characters" />
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" disabled={busy} type="submit">{busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'} <ArrowRight size={16} /></button>
      </form>
      <div className="auth-switch">{mode === 'login' ? 'New to Context OS?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></div>
    </div>
    <div className="auth-footnote"><Sparkles size={14} /> A quieter way to remember.</div>
  </div>
}
