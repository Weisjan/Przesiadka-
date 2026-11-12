import assert from 'node:assert/strict'
import test from 'node:test'
import { directionKey, journeyKey, lineKey, readJourneys, readSearch, readSetup, searchInput, transportName } from '../src/transitData.ts'
import { ApiError, request } from '../src/api.ts'

const departure = {
  operator: 'ztm', operator_name: 'ZTM Gdańsk', stop_id: 'ztm:2001', stop_name: 'Dworzec Główny 01',
  trip_id: 'ztm:b', route_id: 'ztm:6', line: '6', route_type: 900, direction: 'Jelitkowo', direction_id: 0,
  service_id: 'ztm:S', service_date: '2026-11-12', stop_sequence: 13,
  arrival_at: '2026-11-12T17:45:00+01:00', departure_at: '2026-11-12T17:45:00+01:00', pickup_type: 0, drop_off_type: 0,
}
const arrival = { ...departure, operator: 'skm', stop_id: 'skm:7500', trip_id: 'skm:a', service_date: '2026-11-11', stop_sequence: 27 }
const result = {
  margin_minutes: 8, delay_threshold_minutes: 8, status: 'Zdążysz', has_safe_margin: true,
  expected_stop_arrival_at: '2026-11-12T17:37:00+01:00', plan_b_status: 'not_needed', plan_b_departure_at: null,
}
const response = () => ({ is_realtime: false, schedule_status: 'planned', results: [{ departure, evaluation: { ...result }, plan_b: null }],
  search_window: { start_at: '2026-11-12T17:32:00+01:00', end_at_exclusive: '2026-11-12T23:32:00+01:00' }, limitations: ['Dojście szacunkowe.'] })

test('search sends exact trip, service date and stop occurrence without changing instants', () => {
  const payload = searchInput({ id: 'link' }, arrival, departure, 5, 10)
  assert.deepEqual(payload, { link_id: 'link', arrival_trip_id: 'skm:a', arrival_service_date: '2026-11-11', arrival_stop_sequence: 27,
    departure_route_id: 'ztm:6', departure_trip_id: 'ztm:b', departure_service_date: '2026-11-12', departure_stop_sequence: 13,
    walking_minutes: 5, delay_minutes: 10, window_minutes: 360, limit: 1 })
  assert.equal('margin_minutes' in payload, false)
})

test('course identities distinguish service days and repeated stops', () => {
  assert.notEqual(journeyKey(departure), journeyKey({ ...departure, service_date: '2026-11-13' }))
  assert.notEqual(journeyKey(departure), journeyKey({ ...departure, stop_sequence: 14 }))
  assert.notEqual(directionKey(departure), directionKey({ ...departure, direction_id: 1 }))
  assert.equal(lineKey(arrival), '6')
  assert.equal(lineKey(departure), 'ztm:6')
  assert.equal(transportName(900), 'Tramwaj')
  assert.equal(transportName(700), 'Autobus')
})

test('journey lists require static provenance and valid offset-aware times', () => {
  const data = { is_realtime: false, realtime_delay: null, journeys: [departure], has_more: false, source: {} }
  assert.equal(readJourneys(data), data)
  assert.throws(() => readJourneys({ ...data, is_realtime: true }))
  assert.throws(() => readJourneys({ ...data, realtime_delay: 8 }))
  assert.throws(() => readJourneys({ ...data, journeys: [{ ...departure, arrival_at: '17:45' }] }))
  assert.throws(() => readJourneys({ ...data, journeys: [{ ...departure, trip_id: undefined }] }))
})

test('analysis validates backend status and the exact selected departure', () => {
  assert.equal(readSearch(response(), departure).results[0].evaluation.status, 'Zdążysz')
  assert.throws(() => readSearch(response(), { ...departure, service_date: '2026-11-11' }))
  const data = response()
  data.results[0].evaluation.status = 'Almost'
  assert.throws(() => readSearch(data, departure))
  assert.throws(() => readSearch({ ...response(), results: [] }, departure))
  assert.throws(() => readSearch({ ...response(), is_realtime: true }, departure))
})

test('Plan B cannot be invented or disagree with the backend evaluation', () => {
  const data = response()
  data.results[0].evaluation.plan_b_status = 'available'
  data.results[0].evaluation.plan_b_departure_at = '2026-11-12T17:55:00+01:00'
  assert.throws(() => readSearch(data, departure))
  data.results[0].plan_b = { ...departure, trip_id: 'ztm:c', departure_at: '2026-11-12T17:55:00+01:00' }
  assert.equal(readSearch(data, departure).results[0].plan_b.trip_id, 'ztm:c')
  data.results[0].plan_b.departure_at = '2026-11-12T18:55:00+01:00'
  assert.throws(() => readSearch(data, departure))
})

test('setup requires both imported sources and the exact supported stop pair', () => {
  const sources = { is_realtime: false, sources: ['skm', 'ztm'].map(operator => ({ operator, imported: true, name: operator,
    service_start_date: '2026-11-11', service_end_date: '2026-11-25', attribution: 'Source', documentation_url: 'https://example.invalid' })) }
  const links = { is_realtime: false, links: [{ id: 'link', walking_time_source: 'estimated', walking_minutes: null,
    arrival_stop: { stop_id: 'skm:7500', stop_name: 'Gdańsk Główny' }, departure_stop: { stop_id: 'ztm:2001', stop_name: 'Dworzec Główny 01' } }] }
  assert.equal(readSetup(sources, links).link.id, 'link')
  assert.throws(() => readSetup({ ...sources, sources: [sources.sources[0]] }, links))
  assert.throws(() => readSetup(sources, { ...links, links: [{ ...links.links[0], walking_minutes: 5 }] }))
  assert.throws(() => readSetup(sources, { ...links, links: [{ ...links.links[0], departure_stop: { stop_id: 'ztm:2002' } }] }))
})

test('a reimport that changes times is rejected rather than mixing old card times and new results', () => {
  assert.throws(() => readSearch(response(), { ...departure, departure_at: '2026-11-12T17:46:00+01:00' }))
  const data = { ...response(), arrival: { ...arrival, arrival_at: '2026-11-12T17:32:00+01:00' } }
  assert.equal(readSearch(data, departure, { ...arrival, arrival_at: data.arrival.arrival_at }), data)
  assert.throws(() => readSearch(data, departure, { ...arrival, arrival_at: '2026-11-12T17:33:00+01:00' }))
})

test('structured GTFS errors retain their readable explanation, code and HTTP status', async () => {
  const previous = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: { code: 'feed_out_of_range', message: 'Data poza zakresem importu.' } }), { status: 422 })
    await assert.rejects(request('/api/transit/journeys'), error => error instanceof ApiError && error.status === 422
      && error.code === 'feed_out_of_range' && error.message === 'Data poza zakresem importu.')
  } finally { globalThis.fetch = previous }
})
