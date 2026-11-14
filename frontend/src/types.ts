export interface Evaluation {
  margin_minutes: number
  delay_threshold_minutes: number
  status: 'Zdążysz' | 'Na styk' | 'Nie zdążysz'
  has_safe_margin: boolean
  expected_stop_arrival_at: string
}

export function readEvaluation(value: unknown): Evaluation {
  const data = value as Evaluation | null
  const validDate = (date: unknown) => typeof date === 'string' && /[+-]\d{2}:\d{2}$/.test(date) && Number.isFinite(Date.parse(date))
  if (!data || !Number.isFinite(data.margin_minutes) || !Number.isFinite(data.delay_threshold_minutes)
    || !['Zdążysz', 'Na styk', 'Nie zdążysz'].includes(data.status)
    || typeof data.has_safe_margin !== 'boolean' || !validDate(data.expected_stop_arrival_at)
) {
    throw new Error('API zwróciło nieprawidłowy wynik. Spróbuj ponownie.')
  }
  return data
}
