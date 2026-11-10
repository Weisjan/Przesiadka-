export interface Scenario {
  id: number
  name: string
  interchange: string
  arrival_line: string
  departure_line: string
  direction: string
  arrival_at: string
  departure_at: string
  walking_minutes: number
  next_departures: string[]
}

export type ScenarioInput = Omit<Scenario, 'id'>

export interface Evaluation {
  margin_minutes: number
  delay_threshold_minutes: number
  status: 'Zdążysz' | 'Na styk' | 'Nie zdążysz'
  has_safe_margin: boolean
  expected_stop_arrival_at: string
  plan_b_status: 'not_needed' | 'available' | 'unavailable'
  plan_b_departure_at: string | null
}

export function readEvaluation(value: unknown): Evaluation {
  const data = value as Evaluation | null
  const validDate = (date: unknown) => typeof date === 'string' && /[+-]\d{2}:\d{2}$/.test(date) && Number.isFinite(Date.parse(date))
  if (!data || !Number.isFinite(data.margin_minutes) || !Number.isFinite(data.delay_threshold_minutes)
    || !['Zdążysz', 'Na styk', 'Nie zdążysz'].includes(data.status)
    || typeof data.has_safe_margin !== 'boolean' || !validDate(data.expected_stop_arrival_at)
    || !['not_needed', 'available', 'unavailable'].includes(data.plan_b_status)
    || (data.plan_b_status === 'available' ? !validDate(data.plan_b_departure_at) : data.plan_b_departure_at !== null)) {
    throw new Error('API zwróciło nieprawidłowy wynik. Spróbuj ponownie.')
  }
  return data
}
