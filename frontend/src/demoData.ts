import { readStopGroups } from './plannerData.ts'
import type { StopGroup } from './plannerData'

export interface DemoExample {
  id: string; name: string; description: string; origin: StopGroup; destination: StopGroup
  departure_date: string; departure_time: string
}
export interface DemoInfo {
  enabled: true; label: string; departure_date: string; min_departure_time: string; max_departure_time: string
  walking_reference_at: string; examples: DemoExample[]
}
export interface Availability { first: string; last: string; demo: DemoInfo | null }
export function readAvailability(value: unknown): Availability {
  const data = value as { is_realtime?: unknown; sources?: { imported?: unknown; service_start_date?: unknown; service_end_date?: unknown }[]; demo?: DemoInfo | null }
  const date = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)
  const time = (v: unknown): v is string => typeof v === 'string' && /^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(v)
  if (!data || data.is_realtime !== false || !Array.isArray(data.sources) || data.sources.length !== 2
    || !data.sources.every(source => source && source.imported === true && date(source.service_start_date) && date(source.service_end_date))) {
    throw new Error('Brak kompletnych lokalnych rozkładów. Przygotuj dane zgodnie z instrukcją demo.')
  }
  const first = data.sources.map(s => s.service_start_date as string).sort().at(-1)!
  const last = data.sources.map(s => s.service_end_date as string).sort()[0]
  if (first > last) throw new Error('Rozkłady SKM i ZTM nie mają wspólnego zakresu dat.')
  const demo = data.demo ?? null
  if (demo) {
    if (demo.enabled !== true || typeof demo.label !== 'string' || !date(demo.departure_date)
      || !time(demo.min_departure_time) || !time(demo.max_departure_time) || demo.min_departure_time > demo.max_departure_time
      || demo.departure_date < first || demo.departure_date > last
      || !Array.isArray(demo.examples) || demo.examples.length < 1 || demo.examples.length > 3
      || typeof demo.walking_reference_at !== 'string' || !Number.isFinite(Date.parse(demo.walking_reference_at))) throw new Error('Nieprawidłowa konfiguracja archiwalnego demo.')
    for (const example of demo.examples) {
      if (!example || typeof example.id !== 'string' || typeof example.name !== 'string' || typeof example.description !== 'string'
        || example.departure_date !== demo.departure_date || !time(example.departure_time)
        || example.departure_time < demo.min_departure_time || example.departure_time > demo.max_departure_time) throw new Error('Nieprawidłowy przykład demo.')
      readStopGroups({ is_realtime: false, groups: [example.origin], has_more: false }, 'skm')
      readStopGroups({ is_realtime: false, groups: [example.destination], has_more: false }, 'ztm')
    }
    return { first: demo.departure_date, last: demo.departure_date, demo }
  }
  return { first, last, demo: null }
}
