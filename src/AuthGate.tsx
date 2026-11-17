import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, LockKeyhole, Sparkles } from 'lucide-react'
import App from './App'
import { api, setSession, type Session } from './api'

export default function AuthGate() {
  const [session, setCurrent] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  const [resetToken] = useState(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get('reset') || ''
    if (token) window.history.replaceState(null, '', window.location.pathname + window.location.search)
    return token
  })
  const [mode, setMode] = useState<'login' | 'register' | 'recover' | 'reset'>(resetToken ? 'reset' : 'login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

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
    setNotice('')
    try {
      if (mode === 'recover') {
        await api('/auth/recover/request', { method: 'POST', body: JSON.stringify({ email }) })
        setNotice('If an account exists for that email, a recovery link has been sent.')
        return
      }
      if (mode === 'reset') {
        await api('/auth/recover/reset', { method: 'POST', body: JSON.stringify({ token: resetToken, password }) })
        setSession(null)
        setCurrent(null)
        setPassword('')
        setMode('login')
        setNotice('Password changed. Sign in with your new password.')
        return
      }
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
  if (session && mode !== 'reset') return <App session={session} onSignOut={() => { void signOut() }} />

  return <div className="auth-shell">
    <div className="auth-brand"><span className="brand-mark"><span /></span><span>context<span className="brand-os">OS</span></span></div>
    <div className="auth-card">
      <div className="auth-icon"><LockKeyhole size={22} /></div>
      <div className="eyebrow"><span className="eyebrow-dot" /> YOUR PRIVATE MEMORY SPACE</div>
      <h1>{mode === 'login' ? 'Welcome back.' : mode === 'register' ? 'Make room for what matters.' : mode === 'recover' ? 'Find your way back.' : 'Choose a new password.'}</h1>
      <p>{mode === 'login' ? 'Sign in to find everything you saved.' : mode === 'register' ? 'Create your space to save and recover ideas, links, and more.' : mode === 'recover' ? 'Enter your email and we’ll send a one-time recovery link.' : 'Your recovery link can be used once and expires after 30 minutes.'}</p>
      <form onSubmit={event => { void submit(event) }}>
        {mode !== 'reset' && <><label className="field-label" htmlFor="auth-email">Email</label>
        <input id="auth-email" className="field-input" type="email" autoComplete="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com" /></>}
        {mode !== 'recover' && <><label className="field-label" htmlFor="auth-password">{mode === 'reset' ? 'New password' : 'Password'}</label>
        <input id="auth-password" className="field-input" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={12} value={password} onChange={event => setPassword(event.target.value)} placeholder="At least 12 characters" /></>}
        {error && <div className="form-error" role="alert">{error}</div>}
        {notice && <div className="form-notice" role="status">{notice}</div>}
        <button className="primary-button auth-submit" disabled={busy} type="submit">{busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create account' : mode === 'recover' ? 'Send recovery link' : 'Change password'} <ArrowRight size={16} /></button>
      </form>
      <div className="auth-switch">{mode === 'login' ? <>New to Context OS? <button onClick={() => { setMode('register'); setError(''); setNotice('') }}>Create an account</button><br /><button className="auth-recover" onClick={() => { setMode('recover'); setError(''); setNotice('') }}>Forgot password?</button></> : <>Back to <button onClick={() => { setMode('login'); setError(''); setNotice('') }}>sign in</button></>}</div>
    </div>
    <div className="auth-footnote"><Sparkles size={14} /> A quieter way to remember.</div>
  </div>
}
