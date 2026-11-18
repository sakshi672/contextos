type Capture = {
  memory: { id: string; title: string; source_uri: string; status: string; user_note: string; capture_reason: string | null }
  already_saved: boolean
  text_saved: boolean
  project_name: string | null
}
type Settings = { apiOrigin: string; webOrigin: string; token: string; email: string }

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const pair = $<HTMLElement>('pair')
const capture = $<HTMLElement>('capture')
const progress = $<HTMLElement>('progress')
const result = $<HTMLElement>('result')
const failure = $<HTMLElement>('failure')
const message = $<HTMLElement>('message')
const code = $<HTMLInputElement>('code')
const apiOrigin = $<HTMLInputElement>('api-origin')
const webOrigin = $<HTMLInputElement>('web-origin')
const note = $<HTMLTextAreaElement>('note')
const project = $<HTMLInputElement>('project')
let settings: Settings = { apiOrigin: 'http://127.0.0.1:8766', webOrigin: 'http://127.0.0.1:5173', token: '', email: '' }
let current: Capture | null = null
let busy = false

function setMessage(value: string, error = false) {
  message.textContent = value
  message.classList.toggle('error', error)
}

function checkedOrigin(value: string): string {
  const url = new URL(value.trim())
  if (url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
      !(url.protocol === 'https:' || (url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname)))) {
    throw new Error('Use an HTTPS address or a local development address without a path.')
  }
  return url.origin
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(settings.apiOrigin + path, {
    ...options,
    headers: { ...(settings.token ? { Authorization: `Bearer ${settings.token}` } : {}), ...options.headers },
  })
  let body: { data?: T; detail?: string; error?: string }
  try { body = await response.json() } catch { throw new Error('The API did not return a valid response.') }
  if (!response.ok) {
    if (response.status === 401 && settings.token) {
      settings.token = ''
      await chrome.storage.local.remove(['token'])
      showPair()
    }
    throw new Error(body.detail || body.error || `Request failed (${response.status})`)
  }
  return body.data as T
}

function showPair() {
  pair.hidden = false
  capture.hidden = true
  apiOrigin.value = settings.apiOrigin
  webOrigin.value = settings.webOrigin
}

function showCapture() {
  pair.hidden = true
  capture.hidden = false
  $<HTMLElement>('account').textContent = settings.email
}

function visiblePageText(): string {
  const root = document.querySelector('article') || document.querySelector('main') || document.body
  if (!root) return ''
  const forbidden = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG', 'CANVAS',
    'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'BUTTON', 'FORM', 'NAV', 'FOOTER'])
  const visible = (element: Element): boolean => {
    for (let current: Element | null = element; current; current = current.parentElement) {
      if (forbidden.has(current.tagName) || current.hasAttribute('hidden') ||
          current.hasAttribute('inert') || current.getAttribute('aria-hidden') === 'true' ||
          current.hasAttribute('contenteditable')) return false
      const style = getComputedStyle(current)
      if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse' ||
          Number(style.opacity) === 0) return false
      if (current !== document.body && current.getClientRects().length === 0) return false
    }
    return true
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const chunks: string[] = []
  let length = 0
  while (walker.nextNode() && chunks.length < 12000 && length < 600000) {
    const node = walker.currentNode
    if (!node.parentElement || !visible(node.parentElement)) continue
    const value = (node.textContent || '').replace(/\s+/g, ' ').trim()
    if (value.length < 2) continue
    chunks.push(value)
    length += value.length + 1
  }
  let text = chunks.join('\n')
  const encoder = new TextEncoder()
  while (encoder.encode(text).length > 2 * 1024 * 1024) text = text.slice(0, Math.floor(text.length * 0.9))
  return text
}

async function saveCurrentTab() {
  if (busy || !settings.token) return
  busy = true
  current = null
  progress.hidden = false
  result.hidden = true
  failure.hidden = true
  setMessage('')
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id || !tab.url) throw new Error('No active tab is available.')
    const url = new URL(tab.url)
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Only HTTP and HTTPS tabs can be saved.')
    let readableText = ''
    let extractionReason: string | null = null
    try {
      const injected = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: visiblePageText })
      readableText = injected[0]?.result || ''
      if (!readableText) extractionReason = 'no_readable_text'
    } catch {
      extractionReason = 'page_access_restricted'
    }
    const payload = { source_url: tab.url, title: (tab.title || url.hostname).slice(0, 240),
      captured_at: new Date().toISOString(), readable_text: readableText, extraction_reason: extractionReason }
    current = await api<Capture>('/v1/captures', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify(payload),
    })
    progress.hidden = true
    result.hidden = false
    $<HTMLElement>('result-title').textContent = current.already_saved ? 'Already in your library' : 'Saved to your library'
    $<HTMLElement>('result-detail').textContent = current.text_saved ? 'Readable page text saved' :
      'URL and title saved. Page text was unavailable; retry on the page if access changes.'
    $<HTMLButtonElement>('retry-text').hidden = current.text_saved
    $<HTMLElement>('page-title').textContent = current.memory.title
    $<HTMLElement>('page-url').textContent = current.memory.source_uri
    note.value = current.memory.user_note
    project.value = current.project_name || ''
    try {
      const projects = await api<{ names: string[] }>('/v1/extension/projects')
      $<HTMLDataListElement>('projects').replaceChildren(...projects.names.map(name => {
        const option = document.createElement('option')
        option.value = name
        return option
      }))
    } catch { /* The saved capture remains usable without project suggestions. */ }
  } catch (error) {
    progress.hidden = true
    result.hidden = true
    failure.hidden = false
    $<HTMLElement>('failure-detail').textContent = error instanceof Error ? error.message : 'Please try again.'
  } finally { busy = false }
}

$<HTMLButtonElement>('connect').addEventListener('click', async () => {
  const button = $<HTMLButtonElement>('connect')
  button.disabled = true
  setMessage('')
  try {
    const nextApi = checkedOrigin(apiOrigin.value)
    const nextWeb = checkedOrigin(webOrigin.value)
    if (!['127.0.0.1', 'localhost'].includes(new URL(nextApi).hostname)) {
      const allowed = await chrome.permissions.request({ origins: [nextApi + '/*'] })
      if (!allowed) throw new Error('Allow access to your Context OS API to connect.')
    }
    settings.apiOrigin = nextApi
    settings.webOrigin = nextWeb
    const connected = await api<{ token: string; email: string }>('/v1/extension/tokens', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: code.value.trim() }),
    })
    settings.token = connected.token
    settings.email = connected.email
    await chrome.storage.local.set(settings)
    showCapture()
    progress.hidden = true
    result.hidden = true
    failure.hidden = true
    setMessage('Connected. Open a page and click the extension icon to save it.')
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Could not connect.', true)
  } finally { button.disabled = false }
})

$<HTMLButtonElement>('save-details').addEventListener('click', async () => {
  if (!current) return
  const button = $<HTMLButtonElement>('save-details')
  button.disabled = true
  try {
    current = await api<Capture>(`/v1/extension/captures/${current.memory.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_note: note.value, project_name: project.value }),
    })
    setMessage('Note and project saved.')
  } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not save details.', true) }
  finally { button.disabled = false }
})

$<HTMLButtonElement>('screenshot').addEventListener('click', async () => {
  if (!current) return
  const button = $<HTMLButtonElement>('screenshot')
  button.disabled = true
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab || tab.url !== current.memory.source_uri) throw new Error('Return to the saved tab before taking a screenshot.')
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 82 })
    const encoded = dataUrl.split(',')[1]
    if (!encoded) throw new Error('The browser did not return a screenshot.')
    const binary = atob(encoded)
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0))
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    if (blob.size > 20 * 1024 * 1024) throw new Error('Screenshot exceeds 20 MiB.')
    const saved = await api<{ saved: boolean; already_saved: boolean }>(`/v1/extension/captures/${current.memory.id}/screenshot`, {
      method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: blob,
    })
    setMessage(saved.already_saved ? 'Screenshot was already saved.' : 'Visible screenshot saved.')
  } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not save screenshot.', true) }
  finally { button.disabled = false }
})

$<HTMLButtonElement>('open-memory').addEventListener('click', () => {
  if (current) void chrome.tabs.create({ url: settings.webOrigin + '/?memory=' + encodeURIComponent(current.memory.id) })
})
$<HTMLButtonElement>('retry').addEventListener('click', () => { void saveCurrentTab() })
$<HTMLButtonElement>('retry-text').addEventListener('click', () => { void saveCurrentTab() })
$<HTMLButtonElement>('disconnect').addEventListener('click', async () => {
  try { await api('/v1/extension/revoke', { method: 'POST' }) } catch { /* Local disconnect still clears the credential. */ }
  settings.token = ''
  settings.email = ''
  await chrome.storage.local.remove(['token', 'email'])
  showPair()
  setMessage('Extension disconnected.')
})
$<HTMLButtonElement>('settings').addEventListener('click', () => {
  showPair()
  setMessage('Enter a new pairing code to change the connection.')
})

async function boot() {
  const stored = await chrome.storage.local.get(['apiOrigin', 'webOrigin', 'token', 'email'])
  settings = {
    apiOrigin: typeof stored.apiOrigin === 'string' ? stored.apiOrigin : settings.apiOrigin,
    webOrigin: typeof stored.webOrigin === 'string' ? stored.webOrigin : settings.webOrigin,
    token: typeof stored.token === 'string' ? stored.token : '',
    email: typeof stored.email === 'string' ? stored.email : '',
  }
  if (!settings.token) { showPair(); return }
  try {
    const session = await api<{ email: string }>('/v1/extension/session')
    settings.email = session.email
    showCapture()
    await saveCurrentTab()
  } catch (error) {
    showPair()
    setMessage(error instanceof Error ? error.message : 'Connect the extension again.', true)
  }
}
void boot()
