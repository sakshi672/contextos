export type Session = { id: string; email: string; csrf_token: string }

let csrfToken = ''

export function setSession(session: Session | null) {
  csrfToken = session?.csrf_token ?? ''
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const write = options.method && !['GET', 'HEAD'].includes(options.method.toUpperCase())
  const response = await fetch(`/v1${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(write && csrfToken && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')
        ? { 'X-CSRF-Token': csrfToken } : {}),
      ...options.headers,
    },
  })
  let body: { data?: T; detail?: string; error?: string | null }
  try { body = await response.json() } catch { throw new Error('The server did not return a valid response.') }
  if (!response.ok) throw new Error(body.detail || body.error || `Request failed (${response.status})`)
  return body.data as T
}
