export const API_URL = 'http://127.0.0.1:8000'

const fieldLabels: Record<string, string> = {
  name: 'Nazwa scenariusza', interchange: 'Węzeł przesiadkowy', arrival_line: 'Linia przyjazdowa',
  departure_line: 'Linia odjazdowa', direction: 'Kierunek', arrival_at: 'Planowany przyjazd',
  departure_at: 'Planowany odjazd', walking_minutes: 'Czas dojścia', next_departures: 'Kolejne odjazdy',
}

function validationMessage(issue: unknown): string {
  if (typeof issue !== 'object' || issue === null) return 'Sprawdź dane formularza.'
  const { loc, type, msg } = issue as { loc?: unknown[]; type?: string; msg?: string }
  const field = Array.isArray(loc) ? fieldLabels[String(loc[1])] : undefined
  let message = 'Sprawdź wartość i wymagany format.'
  if (type === 'missing') message = 'To pole jest wymagane.'
  if (type === 'string_too_short') message = 'Wpisz co najmniej jeden znak.'
  if (type === 'string_too_long') message = 'Wartość jest zbyt długa.'
  if (type === 'too_long') message = 'Podaj najwyżej 100 kolejnych odjazdów.'
  if (type === 'greater_than_equal' || type === 'less_than_equal' || type === 'int_type') {
    message = 'Podaj całkowitą liczbę minut od 0 do 1440.'
  }
  if (type === 'value_error' && msg?.startsWith('Value error, ')) message = msg.slice(13)
  return field ? `${field}: ${message}` : message
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
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail)) throw new Error([...new Set(detail.map(validationMessage))].join('\n'))
    throw new Error(`Nie udało się wykonać operacji (HTTP ${response.status}). Spróbuj ponownie.`)
  }
  if (response.status === 204) return undefined as T
  return response.json().catch(() => {
    throw new Error('API zwróciło nieprawidłową odpowiedź. Spróbuj ponownie.')
  }) as Promise<T>
}
