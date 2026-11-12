import { readEvaluation } from './types.ts'
import type { Evaluation } from './types'

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
}
export interface TransferLink {
  id: string
  arrival_stop: TransitStop
  departure_stop: TransitStop
  walking_time_source: 'estimated'
  walking_minutes: null
  note: string
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
  results: { departure: Journey; evaluation: Evaluation; plan_b: Journey | null }[]
  search_window: { start_at: string; end_at_exclusive: string }
  limitations: string[]
}

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null
const date = (value: unknown): value is string => typeof value === 'string' && /[+-]\d{2}:\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
export const journeyKey = (item: Journey) => JSON.stringify([item.trip_id, item.service_date, item.stop_sequence])
export const lineKey = (item: Journey) => item.operator === 'skm' ? item.line : item.route_id
export const directionKey = (item: Journey) => JSON.stringify([item.direction_id, item.direction])
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

export function readSetup(sources: unknown, links: unknown): { sources: TransitSource[]; link: TransferLink } {
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
  const link = links.links[0]
  if (!record(link) || typeof link.id !== 'string' || link.walking_time_source !== 'estimated' || link.walking_minutes !== null
    || !record(link.arrival_stop) || link.arrival_stop.stop_id !== 'skm:7500' || typeof link.arrival_stop.stop_name !== 'string'
    || !record(link.departure_stop) || link.departure_stop.stop_id !== 'ztm:2001' || typeof link.departure_stop.stop_name !== 'string') {
    throw new Error('API nie udostępnia obsługiwanego powiązania SKM → ZTM.')
  }
  return { sources: providers as TransitSource[], link: link as unknown as TransferLink }
}

export function readJourneys(value: unknown): JourneysResponse {
  if (!record(value) || value.is_realtime !== false || value.realtime_delay !== null
    || !Array.isArray(value.journeys) || value.journeys.length > 2000 || !value.journeys.every(validJourney)
    || typeof value.has_more !== 'boolean' || !record(value.source)) {
    throw new Error('API zwróciło nieprawidłową listę kursów. Ponów wybór.')
  }
  return value as unknown as JourneysResponse
}

export function readSearch(value: unknown, selected: Journey, expectedArrival?: Journey): SearchResponse {
  if (!record(value) || value.is_realtime !== false || value.schedule_status !== 'planned'
    || !Array.isArray(value.results) || value.results.length !== 1 || !record(value.search_window)
    || !date(value.search_window.start_at) || !date(value.search_window.end_at_exclusive)
    || !Array.isArray(value.limitations) || !value.limitations.every(item => typeof item === 'string')) {
    throw new Error('API nie zwróciło oceny wybranego kursu. Wybierz kurs ponownie.')
  }
  const item = value.results[0]
  if (!record(item) || !validJourney(item.departure) || journeyKey(item.departure) !== journeyKey(selected)
    || item.departure.stop_id !== selected.stop_id || item.departure.route_id !== selected.route_id
    || item.departure.departure_at !== selected.departure_at
    || (item.plan_b !== null && !validJourney(item.plan_b))) throw new Error('Odpowiedź API dotyczy innego lub nieprawidłowego kursu.')
  if (expectedArrival && (!record(value.arrival) || value.arrival.trip_id !== expectedArrival.trip_id
    || value.arrival.service_date !== expectedArrival.service_date || value.arrival.stop_sequence !== expectedArrival.stop_sequence
    || value.arrival.arrival_at !== expectedArrival.arrival_at)) throw new Error('Rozkład przyjazdu zmienił się. Wybierz kurs ponownie.')
  const evaluation = readEvaluation(item.evaluation)
  if ((evaluation.plan_b_status === 'available') !== (item.plan_b !== null)
    || (item.plan_b && (item.plan_b.route_id !== selected.route_id || item.plan_b.stop_id !== selected.stop_id || item.plan_b.direction_id !== selected.direction_id))
    || (item.plan_b && Date.parse(item.plan_b.departure_at ?? '') !== Date.parse(evaluation.plan_b_departure_at ?? ''))) {
    throw new Error('API zwróciło niespójny Plan B.')
  }
  return value as unknown as SearchResponse
}

export function searchInput(link: TransferLink, arrival: Journey, departure: Journey, walking: number, delay: number) {
  return {
    link_id: link.id, arrival_trip_id: arrival.trip_id, arrival_service_date: arrival.service_date,
    arrival_stop_sequence: arrival.stop_sequence, departure_route_id: departure.route_id,
    departure_trip_id: departure.trip_id, departure_service_date: departure.service_date,
    departure_stop_sequence: departure.stop_sequence, walking_minutes: walking, delay_minutes: delay,
    window_minutes: 360, limit: 1,
  }
}
