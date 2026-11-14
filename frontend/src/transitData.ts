import { readEvaluation } from './types.ts'
import type { Evaluation } from './types'
import { readWalking } from './walkingData.ts'
import type { WalkingResponse } from './walkingData'

export type Leg = 'arrival' | 'departure'
export interface TransitSource {
  operator: 'skm' | 'ztm'
  name: string
  imported: boolean
  service_start_date?: string
  service_end_date?: string
  downloaded_at?: string | null
  imported_at?: string
  attribution: string
  documentation_url: string
}
export interface TransitStop {
  operator: 'skm' | 'ztm'
  stop_id: string
  stop_name: string
  location_type: number
  parent_station: string | null
  stop_code?: string
}
export interface TransferLink {
  id: string
  arrival_stop: TransitStop
  departure_stop: TransitStop
  walking_time_source: 'estimated'
  note: string
  approval_status: 'approved'
  walking?: WalkingResponse | { status: 'error'; message: string }
}
export interface Journey {
  operator: 'skm' | 'ztm'
  operator_name: string
  stop_id: string
  stop_name: string
  trip_id: string
  route_id: string
  line: string
  route_type: number
  direction: string | null
  direction_id: number | null
  service_id: string
  service_date: string
  stop_sequence: number
  arrival_at: string | null
  departure_at: string | null
  pickup_type: number
  drop_off_type: number
}
export interface JourneysResponse {
  is_realtime: false
  realtime_delay: null
  journeys: Journey[]
  has_more: boolean
  source: TransitSource
}
export interface SearchResponse {
  is_realtime: false
  schedule_status: 'planned'
  results: { departure: Journey; evaluation: Evaluation }[]
  search_window: { start_at: string; end_at_exclusive: string }
  limitations: string[]
  link?: { id: string; walking_minutes: number; walking_time_basis: 'user_input' | 'openrouteservice_cache' }
}

export interface SuggestedTransfer {
  link: TransferLink & { walking_minutes: number; walking: WalkingResponse }
  departure: Journey
  evaluation: Evaluation
  match: { kind: 'line' | 'direction' | 'stop'; stop_id?: string; stop_name?: string }
}

export interface SuggestionsResponse {
  is_realtime: false
  schedule_status: 'planned'
  query: string
  outcome: 'choose_destination' | 'recommended' | 'no_reachable' | 'no_match' | 'walking_unavailable'
  recommendation: SuggestedTransfer | null
  results: SuggestedTransfer[]
  directions: { line: string; direction: string; query: string }[]
  reason: string | null
  has_more: boolean
  excluded_links: { link_id: string; status: string; message: string }[]
  limitations: string[]
}

export function suggestionInput(arrival: Journey, query: string) {
  return { arrival_stop_id: arrival.stop_id, arrival_trip_id: arrival.trip_id, arrival_service_date: arrival.service_date,
    arrival_stop_sequence: arrival.stop_sequence, query: query.trim(), delay_minutes: 0 }
}

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null
const date = (value: unknown): value is string => typeof value === 'string' && /[+-]\d{2}:\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
export const journeyKey = (item: Journey) => JSON.stringify([item.trip_id, item.service_date, item.stop_sequence])
export const lineKey = (item: Journey) => item.operator === 'skm' ? item.line : item.route_id
export const directionKey = (item: Journey) => JSON.stringify([item.direction_id, item.direction])
export const stopLabel = (stop: TransitStop) => `${stop.stop_name} · ${stop.stop_code ? `kod ${stop.stop_code}` : stop.stop_id}`
export const transportName = (type: number) => type === 0 || (type >= 900 && type < 1000) ? 'Tramwaj'
  : type === 3 || (type >= 700 && type < 800) ? 'Autobus' : type === 2 || (type >= 100 && type < 200) ? 'Kolej' : 'Przejazd'

function validJourney(value: unknown): value is Journey {
  if (!record(value)) return false
  return ['skm', 'ztm'].includes(String(value.operator))
    && ['operator_name', 'stop_id', 'stop_name', 'trip_id', 'route_id', 'line', 'service_id', 'service_date'].every(key => typeof value[key] === 'string' && value[key] !== '')
    && /^\d{4}-\d{2}-\d{2}$/.test(String(value.service_date))
    && Number.isInteger(value.stop_sequence) && Number.isInteger(value.route_type)
    && (value.direction === null || typeof value.direction === 'string')
    && (value.direction_id === null || value.direction_id === 0 || value.direction_id === 1)
    && (value.arrival_at === null || date(value.arrival_at)) && (value.departure_at === null || date(value.departure_at))
    && (date(value.arrival_at) || date(value.departure_at))
    && typeof value.pickup_type === 'number' && [0, 1, 2, 3].includes(value.pickup_type)
    && typeof value.drop_off_type === 'number' && [0, 1, 2, 3].includes(value.drop_off_type)
}

export function readSetup(sources: unknown, links: unknown): { sources: TransitSource[]; link: TransferLink; links: TransferLink[] } {
  if (!record(sources) || sources.is_realtime !== false || !Array.isArray(sources.sources)
    || !record(links) || links.is_realtime !== false || !Array.isArray(links.links)) throw new Error('Nieprawidłowa odpowiedź o lokalnych rozkładach.')
  const providers = sources.sources
  for (const operator of ['skm', 'ztm']) {
    const source = providers.find(item => record(item) && item.operator === operator)
    if (!record(source) || source.imported !== true || typeof source.name !== 'string'
      || typeof source.service_start_date !== 'string' || typeof source.service_end_date !== 'string'
      || typeof source.attribution !== 'string' || typeof source.documentation_url !== 'string' || !source.documentation_url.startsWith('https://')) {
      throw new Error('Brak poprawnych lokalnych rozkładów SKM i ZTM. Wykonaj import opisany w README.')
    }
  }
  if (!links.links.length || links.links.length > 100) throw new Error('API nie udostępnia zatwierdzonych powiązań SKM → ZTM.')
  const ids = new Set<string>()
  for (const link of links.links) {
    if (!record(link) || typeof link.id !== 'string' || !link.id || ids.has(link.id)
      || link.walking_time_source !== 'estimated'
      || link.approval_status !== 'approved'
      || !record(link.arrival_stop) || !String(link.arrival_stop.stop_id).startsWith('skm:') || typeof link.arrival_stop.stop_name !== 'string'
      || !record(link.departure_stop) || !String(link.departure_stop.stop_id).startsWith('ztm:') || typeof link.departure_stop.stop_name !== 'string') {
      throw new Error('API nie udostępnia poprawnego zatwierdzonego powiązania SKM → ZTM.')
    }
    ids.add(link.id)
    if (link.walking !== undefined) {
      if (record(link.walking) && link.walking.status === 'error' && typeof link.walking.message === 'string') continue
      readWalking(link.walking, String(link.arrival_stop.stop_id), String(link.departure_stop.stop_id))
    }
  }
  const approved = links.links as unknown as TransferLink[]
  return { sources: providers as TransitSource[], link: approved[0], links: approved }
}

export function readJourneys(value: unknown): JourneysResponse {
  if (!record(value) || value.is_realtime !== false || value.realtime_delay !== null
    || !Array.isArray(value.journeys) || value.journeys.length > 2000 || !value.journeys.every(validJourney)
    || typeof value.has_more !== 'boolean' || !record(value.source)) {
    throw new Error('API zwróciło nieprawidłową listę kursów. Ponów wybór.')
  }
  return value as unknown as JourneysResponse
}

export function readSuggestions(value: unknown, arrival: Journey, query: string, links: TransferLink[]): SuggestionsResponse {
  if (!record(value) || value.is_realtime !== false || value.schedule_status !== 'planned' || value.query !== query.trim()
    || !record(value.arrival) || value.arrival.stop_id !== arrival.stop_id || value.arrival.trip_id !== arrival.trip_id
    || value.arrival.service_date !== arrival.service_date || value.arrival.stop_sequence !== arrival.stop_sequence
    || value.arrival.route_id !== arrival.route_id || value.arrival.arrival_at !== arrival.arrival_at
    || !['choose_destination', 'recommended', 'no_reachable', 'no_match', 'walking_unavailable'].includes(String(value.outcome))
    || !Array.isArray(value.results) || value.results.length > 20 || !Array.isArray(value.directions) || value.directions.length > 12
    || !value.directions.every(item => record(item) && ['line', 'direction', 'query'].every(key => typeof item[key] === 'string' && item[key] !== ''))
    || !Array.isArray(value.excluded_links) || !value.excluded_links.every(item => record(item)
      && ['link_id', 'status', 'message'].every(key => typeof item[key] === 'string'))
    || !Array.isArray(value.limitations) || !value.limitations.every(item => typeof item === 'string')
    || !(value.reason === null || typeof value.reason === 'string') || typeof value.has_more !== 'boolean') {
    throw new Error('API zwróciło nieprawidłowe propozycje. Wybierz pociąg ponownie.')
  }
  function validate(item: unknown): asserts item is SuggestedTransfer {
    if (!record(item) || !record(item.link) || !validJourney(item.departure) || item.departure.operator !== 'ztm'
      || !record(item.match) || !['line', 'direction', 'stop'].includes(String(item.match.kind))) {
      throw new Error('API zwróciło nieprawidłową propozycję kursu.')
    }
    const approved = links.find(link => link.id === (item.link as Record<string, unknown>).id)
    const link = item.link
    if (!approved || approved.arrival_stop.stop_id !== arrival.stop_id
      || approved.departure_stop.stop_id !== item.departure.stop_id || !record(link.arrival_stop) || !record(link.departure_stop)
      || link.arrival_stop.stop_id !== arrival.stop_id || link.departure_stop.stop_id !== item.departure.stop_id) {
      throw new Error('Propozycja dotyczy innego lub niezatwierdzonego przystanku.')
    }
    const walking = readWalking(link.walking, arrival.stop_id, item.departure.stop_id)
    if (walking.status !== 'available' || walking.estimate?.walking_minutes !== link.walking_minutes) {
      throw new Error('Propozycja nie ma aktualnego szacunku dojścia.')
    }
    readEvaluation(item.evaluation)
  }
  value.results.forEach(validate)
  if (value.recommendation !== null) {
    validate(value.recommendation)
    const chosen = value.recommendation
    if (value.outcome !== 'recommended' || !query.trim() || chosen.evaluation.margin_minutes < 0
      || !value.results.some(item => record(item) && record(item.link) && validJourney(item.departure)
        && item.link.id === chosen.link.id && journeyKey(item.departure) === journeyKey(chosen.departure))) {
      throw new Error('API zwróciło niespójną rekomendację.')
    }
  } else if (value.outcome === 'recommended') throw new Error('API nie zwróciło rekomendowanego kursu.')
  return value as unknown as SuggestionsResponse
}

export function readSearch(value: unknown, selected: Journey, expectedArrival?: Journey, expectedLink?: TransferLink,
                           expectedWalking?: number): SearchResponse {
  if (!record(value) || value.is_realtime !== false || value.schedule_status !== 'planned'
    || !Array.isArray(value.results) || value.results.length !== 1 || !record(value.search_window)
    || !date(value.search_window.start_at) || !date(value.search_window.end_at_exclusive)
    || !Array.isArray(value.limitations) || !value.limitations.every(item => typeof item === 'string')) {
    throw new Error('API nie zwróciło oceny wybranego kursu. Wybierz kurs ponownie.')
  }
  const item = value.results[0]
  if (!record(item) || !validJourney(item.departure) || journeyKey(item.departure) !== journeyKey(selected)
    || item.departure.stop_id !== selected.stop_id || item.departure.route_id !== selected.route_id
    || item.departure.departure_at !== selected.departure_at) throw new Error('Odpowiedź API dotyczy innego lub nieprawidłowego kursu.')
  if (expectedArrival && (!record(value.arrival) || value.arrival.trip_id !== expectedArrival.trip_id
    || value.arrival.stop_id !== expectedArrival.stop_id || value.arrival.route_id !== expectedArrival.route_id
    || value.arrival.service_date !== expectedArrival.service_date || value.arrival.stop_sequence !== expectedArrival.stop_sequence
    || value.arrival.arrival_at !== expectedArrival.arrival_at)) throw new Error('Rozkład przyjazdu zmienił się. Wybierz kurs ponownie.')
  if (expectedLink && (!record(value.link) || value.link.id !== expectedLink.id
    || value.link.walking_minutes !== expectedWalking)) {
    throw new Error('Powiązanie lub szacunek dojścia zmienił się. Odśwież propozycje, aby odczytać aktualny szacunek.')
  }
  readEvaluation(item.evaluation)
  return value as unknown as SearchResponse
}

export function searchInput(link: TransferLink, arrival: Journey, departure: Journey, delay: number) {
  return {
    link_id: link.id, arrival_trip_id: arrival.trip_id, arrival_service_date: arrival.service_date,
    arrival_stop_sequence: arrival.stop_sequence, departure_route_id: departure.route_id,
    departure_trip_id: departure.trip_id, departure_service_date: departure.service_date,
    departure_stop_sequence: departure.stop_sequence, delay_minutes: delay,
  }
}
