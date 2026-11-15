export const API_URL = 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  const timeout = AbortSignal.timeout(10000)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
  const response = await fetch(`${API_URL}${path}`, { ...options, headers, signal, cache: 'no-store' })
    .catch(() => { throw new Error('Nie udało się połączyć z API. Sprawdź backend i spróbuj ponownie.') })
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: unknown } | null
    const detail = data?.detail
    if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'message' in detail && typeof detail.message === 'string') {
      throw new ApiError(detail.message, response.status, 'code' in detail && typeof detail.code === 'string' ? detail.code : undefined)
    }
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail)) throw new Error([...new Set(detail.map(() => 'Sprawdź parametry kursu i datę.'))].join('\n'))
    throw new Error(`Nie udało się wykonać operacji (HTTP ${response.status}). Spróbuj ponownie.`)
  }
  if (response.status === 204) return undefined as T
  return response.json().catch(() => {
    throw new Error('API zwróciło nieprawidłową odpowiedź. Spróbuj ponownie.')
  }) as Promise<T>
}
