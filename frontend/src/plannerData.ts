import { fromIso } from './dates.ts'
import { readSearch, validJourney } from './transitData.ts'
import type { Journey, SuggestedTransfer, TransitStop, TransitSource } from './transitData'
import { readEvaluation } from './types.ts'
import { readWalking } from './walkingData.ts'

export interface StopGroup { name: string; operator: 'skm' | 'ztm'; stops: TransitStop[] }
export interface PlanInput {
  origin_stop_ids: string[]; destination_stop_ids: string[]; departure_date: string; departure_time: string
  departure_offset?: string; max_results: number
}
export interface PlannedJourney {
  origin: Journey; arrival: Journey; departure: Journey; destination: Journey
  link: SuggestedTransfer['link']; evaluation: SuggestedTransfer['evaluation']
  total_minutes: number; waiting_minutes: number; elapsed_from_request_minutes: number; initial_wait_minutes: number
  risk: 'estimated' | 'tight'
}
export interface PlanResponse {
  is_realtime: false; schedule_status: 'planned'; outcome: string; results: PlannedJourney[]
  reason: string; limitations: string[]; sources: TransitSource[]; has_more: boolean
  requested_departure_at: string; scope: { approved_links: number; available_links: number }
}
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const iso = (v: unknown): v is string => typeof v === 'string' && /[+-]\d{2}:\d{2}$/.test(v) && Number.isFinite(Date.parse(v))
const nonnegative = (v: unknown) => typeof v === 'number' && Number.isFinite(v) && v >= 0
const sameIDs = (a: unknown, b: string[]) => Array.isArray(a) && JSON.stringify([...a].sort()) === JSON.stringify([...b].sort())
export const planIdentity = (p: PlannedJourney) => JSON.stringify([p.origin.trip_id, p.origin.service_date, p.origin.stop_sequence,
  p.arrival.stop_sequence, p.link.id, p.departure.trip_id, p.departure.service_date, p.departure.stop_sequence, p.destination.stop_sequence])

export function readStopGroups(value: unknown, operator: 'skm' | 'ztm'): { groups: StopGroup[]; has_more: boolean } {
  if (!record(value) || value.is_realtime !== false || !Array.isArray(value.groups) || value.groups.length > 100
    || typeof value.has_more !== 'boolean' || !value.groups.every(g => record(g) && g.operator === operator
      && typeof g.name === 'string' && g.name.length > 0 && Array.isArray(g.stops) && g.stops.length > 0 && g.stops.length <= 32
      && g.stops.every(s => record(s) && s.operator === operator && typeof s.stop_name === 'string'
        && typeof s.stop_id === 'string' && s.stop_id.startsWith(`${operator}:`)))) {
    throw new Error('Nieprawidłowa lista przystanków. Spróbuj ponownie.')
  }
  return value as unknown as { groups: StopGroup[]; has_more: boolean }
}

export function readPlan(value: unknown, input: PlanInput): PlanResponse {
  if (!record(value) || value.is_realtime !== false || value.schedule_status !== 'planned'
    || !sameIDs(value.origin_stop_ids, input.origin_stop_ids) || !sameIDs(value.destination_stop_ids, input.destination_stop_ids)
    || !iso(value.requested_departure_at) || fromIso(value.requested_departure_at).date !== input.departure_date
    || fromIso(value.requested_departure_at).time !== input.departure_time
    || (input.departure_offset && !value.requested_departure_at.endsWith(input.departure_offset))
    || !Array.isArray(value.results) || value.results.length > input.max_results
    || !['found', 'no_skm', 'no_transfer_link', 'walking_unavailable', 'no_destination_service', 'no_reachable'].includes(String(value.outcome))
    || (value.outcome === 'found') !== (value.results.length > 0)
    || typeof value.reason !== 'string' || typeof value.has_more !== 'boolean'
    || !Array.isArray(value.limitations) || !value.limitations.every(x => typeof x === 'string')
    || !Array.isArray(value.sources) || !['skm', 'ztm'].every(operator => value.sources instanceof Array && value.sources.some(s => record(s)
      && s.operator === operator && s.imported === true && typeof s.attribution === 'string'
      && typeof s.documentation_url === 'string' && s.documentation_url.startsWith('https://')
      && typeof s.sha256 === 'string' && /^[a-f0-9]{64}$/.test(s.sha256) && iso(s.imported_at)
      && typeof s.service_start_date === 'string' && typeof s.service_end_date === 'string'))
    || !record(value.scope) || !nonnegative(value.scope.approved_links) || !nonnegative(value.scope.available_links)) {
    throw new Error('Odpowiedź nie dotyczy aktualnie wyszukiwanej podróży. Wyszukaj ponownie.')
  }
  for (const item of value.results) {
    if (!record(item) || !validJourney(item.origin) || !validJourney(item.arrival) || !validJourney(item.departure) || !validJourney(item.destination)
      || item.origin.operator !== 'skm' || item.arrival.operator !== 'skm' || item.departure.operator !== 'ztm' || item.destination.operator !== 'ztm'
      || !input.origin_stop_ids.includes(item.origin.stop_id) || !input.destination_stop_ids.includes(item.destination.stop_id)
      || item.origin.trip_id !== item.arrival.trip_id || item.origin.route_id !== item.arrival.route_id || item.origin.service_date !== item.arrival.service_date
      || item.origin.stop_sequence >= item.arrival.stop_sequence
      || item.departure.trip_id !== item.destination.trip_id || item.departure.route_id !== item.destination.route_id
      || item.departure.service_date !== item.destination.service_date || item.departure.stop_sequence >= item.destination.stop_sequence
      || !record(item.link) || item.link.approval_status !== 'approved' || typeof item.link.id !== 'string'
      || !record(item.link.arrival_stop) || !record(item.link.departure_stop)
      || item.link.arrival_stop.stop_id !== item.arrival.stop_id || item.link.departure_stop.stop_id !== item.departure.stop_id
      || ![item.total_minutes, item.waiting_minutes, item.initial_wait_minutes, item.elapsed_from_request_minutes].every(nonnegative)
      || !['estimated', 'tight'].includes(String(item.risk))) throw new Error('API zwróciło niespójne etapy podróży.')
    const times = [value.requested_departure_at, item.origin.departure_at, item.arrival.arrival_at, item.departure.departure_at, item.destination.arrival_at]
    if (!times.every(iso) || times.some((t, i) => i > 0 && Date.parse(t!) < Date.parse(times[i - 1]!))) {
      throw new Error('API zwróciło nieprawidłową kolejność czasów podróży.')
    }
    const walking = readWalking(item.link.walking, item.arrival.stop_id, item.departure.stop_id)
    if (walking.status !== 'available' || walking.estimate?.walking_minutes !== item.link.walking_minutes) throw new Error('Brak aktualnego dojścia dla podróży.')
    if (readEvaluation(item.evaluation).margin_minutes < 0) throw new Error('API zaproponowało nieosiągalną przesiadkę.')
  }
  return value as unknown as PlanResponse
}

export function readPlannedEvaluation(value: unknown, plan: PlannedJourney, sources: TransitSource[]) {
  const result = readSearch(value, plan.departure, plan.arrival, plan.link, plan.link.walking_minutes)
  if (!record(value) || !Array.isArray(value.sources) || !sources.every(source => value.sources instanceof Array
    && value.sources.some(current => record(current) && current.operator === source.operator
      && current.sha256 === source.sha256 && current.imported_at === source.imported_at))) {
    throw new Error('Rozkład zmienił się od wyszukania podróży. Wyszukaj ponownie, aby odświeżyć wszystkie etapy.')
  }
  return result
}
