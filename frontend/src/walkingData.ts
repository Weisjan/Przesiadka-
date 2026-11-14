export interface WalkingEstimate {
  status: 'available' | 'no_route'
  source: 'openrouteservice'
  confidence: 'estimated'
  walking_seconds: number | null
  walking_minutes: number | null
  distance_m: number | null
  calculated_at: string
  expires_at: string
  attribution: string
  license: 'CC-BY-SA-4.0'
  license_url: string
  terms_url: string
  rounding: 'ceil_to_full_minutes'
}

export interface WalkingResponse {
  status: 'available' | 'missing' | 'stale' | 'no_route'
  from_stop_id: string
  to_stop_id: string
  estimate: WalkingEstimate | null
}

export function readWalking(value: unknown, from: string, to: string): WalkingResponse {
  const data = value as WalkingResponse | null
  if (!data || data.from_stop_id !== from || data.to_stop_id !== to || !['available', 'missing', 'stale', 'no_route'].includes(data.status)) {
    throw new Error('API zwróciło nieprawidłowy szacunek dojścia.')
  }
  if (data.status === 'missing') {
    if (data.estimate !== null) throw new Error('API zwróciło niespójny stan dojścia.')
    return data
  }
  const estimate = data.estimate
  const date = (value: unknown) => typeof value === 'string' && /[+-]\d{2}:\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
  if (!estimate || estimate.source !== 'openrouteservice' || estimate.confidence !== 'estimated'
    || !['available', 'no_route'].includes(estimate.status) || !date(estimate.calculated_at) || !date(estimate.expires_at)
    || estimate.license !== 'CC-BY-SA-4.0' || typeof estimate.attribution !== 'string'
    || estimate.license_url !== 'https://creativecommons.org/licenses/by-sa/4.0/'
    || estimate.terms_url !== 'https://account.heigit.org/info/tos' || estimate.rounding !== 'ceil_to_full_minutes') {
    throw new Error('API nie potwierdza źródła i szacunkowego charakteru dojścia.')
  }
  if (data.status !== 'stale' && data.status !== estimate.status) throw new Error('API zwróciło niespójny stan dojścia.')
  if (estimate.status === 'available') {
    if (typeof estimate.walking_seconds !== 'number' || !Number.isFinite(estimate.walking_seconds) || estimate.walking_seconds <= 0
      || typeof estimate.distance_m !== 'number' || !Number.isFinite(estimate.distance_m) || estimate.distance_m <= 0
      || !Number.isInteger(estimate.walking_minutes) || estimate.walking_minutes! < 1 || estimate.walking_minutes! > 180) {
      throw new Error('API zwróciło nieprawidłowy czas lub odległość dojścia.')
    }
  } else if (estimate.walking_seconds !== null || estimate.walking_minutes !== null || estimate.distance_m !== null) {
    throw new Error('Brak trasy nie może być reprezentowany zerowym czasem dojścia.')
  }
  return data
}
