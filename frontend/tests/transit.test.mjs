import assert from 'node:assert/strict'
import test from 'node:test'
import { directionKey, journeyKey, lineKey, readJourneys, readSearch, readSetup, readSuggestions, searchInput, suggestionInput, stopLabel, transportName } from '../src/transitData.ts'
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
  expected_stop_arrival_at: '2026-11-12T17:37:00+01:00',
}
const response = () => ({ is_realtime: false, schedule_status: 'planned', results: [{ departure, evaluation: { ...result } }],
  search_window: { start_at: '2026-11-12T17:32:00+01:00', end_at_exclusive: '2026-11-12T23:32:00+01:00' }, limitations: ['Dojście szacunkowe.'] })

test('search sends exact trip, service date and stop occurrence without changing instants', () => {
  const payload = searchInput({ id: 'link' }, arrival, departure, 10)
  assert.deepEqual(payload, { link_id: 'link', arrival_trip_id: 'skm:a', arrival_service_date: '2026-11-11', arrival_stop_sequence: 27,
    departure_route_id: 'ztm:6', departure_trip_id: 'ztm:b', departure_service_date: '2026-11-12', departure_stop_sequence: 13,
    delay_minutes: 10,  })
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

test('setup requires both imported sources and directional links returned by the approved-link API', () => {
  const sources = { is_realtime: false, sources: ['skm', 'ztm'].map(operator => ({ operator, imported: true, name: operator,
    service_start_date: '2026-11-11', service_end_date: '2026-11-25', attribution: 'Source', documentation_url: 'https://example.invalid' })) }
  const links = { is_realtime: false, links: [{ id: 'link', approval_status: 'approved', walking_time_source: 'estimated', walking_minutes: null,
    arrival_stop: { stop_id: 'skm:7500', stop_name: 'Gdańsk Główny' }, departure_stop: { stop_id: 'ztm:2001', stop_name: 'Dworzec Główny 01' } }] }
  assert.equal(readSetup(sources, links).link.id, 'link')
  assert.throws(() => readSetup({ ...sources, sources: [sources.sources[0]] }, links))
  assert.throws(() => readSetup(sources, { ...links, links: [{ ...links.links[0], approval_status: 'candidate' }] }))
  assert.throws(() => readSetup(sources, { ...links, links: [{ ...links.links[0], departure_stop: { stop_id: 'skm:7500', stop_name: 'Wrong direction' } }] }))
  const multiple = { ...links, links: ['2001', '2135', '2136', '1021'].map(stop => ({ ...links.links[0], id: `approved-${stop}`, approval_status: 'approved',
    departure_stop: { stop_id: `ztm:${stop}`, stop_name: `Fixture stop ${stop}`, stop_code: stop } })) }
  const parsed = readSetup(sources, multiple)
  assert.equal(parsed.links.length, 4)
  assert.equal(parsed.link.id, 'approved-2001')
  assert.equal(stopLabel(parsed.links[1].departure_stop), 'Fixture stop 2135 · kod 2135')
  assert.equal(stopLabel({ stop_name: 'Gdańsk Główny', stop_id: 'skm:7500', stop_code: '' }), 'Gdańsk Główny · skm:7500')
  assert.throws(() => readSetup(sources, { ...multiple, links: [multiple.links[0], multiple.links[0]] }))
})

test('responses for a different link or a changed walking estimate cannot replace the current result', () => {
  const data = { ...response(), link: { id: 'pair-a', walking_minutes: 3 }, arrival }
  assert.equal(readSearch(data, departure, arrival, { id: 'pair-a' }, 3), data)
  assert.throws(() => readSearch(data, departure, arrival, { id: 'pair-b' }, 3))
  assert.throws(() => readSearch(data, departure, arrival, { id: 'pair-a' }, 7))
  assert.throws(() => readSearch({ ...data, arrival: { ...arrival, stop_id: 'skm:other' } }, departure, arrival))
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

const walking = { status: 'available', from_stop_id: arrival.stop_id, to_stop_id: departure.stop_id,
  estimate: { status: 'available', source: 'openrouteservice', confidence: 'estimated', walking_seconds: 153.7, walking_minutes: 3, distance_m: 213.5,
    calculated_at: '2026-11-12T00:00:00+01:00', expires_at: '2026-12-12T00:00:00+01:00', attribution: 'Test fixture',
    license: 'CC-BY-SA-4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0/',
    terms_url: 'https://account.heigit.org/info/tos', rounding: 'ceil_to_full_minutes' } }
const link = { id: 'approved', arrival_stop: { stop_id: arrival.stop_id }, departure_stop: { stop_id: departure.stop_id },
  walking_time_source: 'estimated', approval_status: 'approved', walking, walking_minutes: 3 }
const suggestion = () => {
  const item = { link, departure, evaluation: result, match: { kind: 'line' } }
  return { is_realtime: false, schedule_status: 'planned', arrival, query: '6', outcome: 'recommended', recommendation: item,
    results: [item], directions: [], reason: 'Prefer a two-minute margin.', has_more: false, excluded_links: [], limitations: [] }
}

test('suggestions send exact SKM occurrence and a trimmed goal, with zero initial delay', () => {
  assert.deepEqual(suggestionInput(arrival, ' 6 '), { arrival_stop_id: arrival.stop_id, arrival_trip_id: arrival.trip_id,
    arrival_service_date: arrival.service_date, arrival_stop_sequence: arrival.stop_sequence, query: '6', delay_minutes: 0 })
})

test('suggestions reject stale goals, other arrivals, unapproved poles and expired walking', () => {
  const data = suggestion()
  assert.equal(readSuggestions(data, arrival, '6', [link]), data)
  assert.throws(() => readSuggestions(data, arrival, '8', [link]))
  assert.throws(() => readSuggestions(data, { ...arrival, service_date: '2026-11-13' }, '6', [link]))
  assert.throws(() => readSuggestions(data, { ...arrival, arrival_at: '2026-11-12T17:46:00+01:00' }, '6', [link]))
  assert.throws(() => readSuggestions(data, arrival, '6', []))
  const stale = suggestion()
  stale.results = [{ ...stale.results[0], link: { ...link, walking: { ...walking, status: 'stale' } } }]
  assert.throws(() => readSuggestions(stale, arrival, '6', [link]))
  const impossible = suggestion()
  impossible.recommendation = { ...impossible.recommendation, evaluation: { ...result, margin_minutes: -1 } }
  assert.throws(() => readSuggestions(impossible, arrival, '6', [link]))
})

test('empty goals expose directions without inventing a recommendation', () => {
  const data = { ...suggestion(), query: '', outcome: 'choose_destination', results: [], recommendation: null,
    directions: [{ line: '6', direction: 'Jelitkowo', query: '6 Jelitkowo' }] }
  assert.equal(readSuggestions(data, arrival, '', [link]).recommendation, null)
  assert.throws(() => readSuggestions({ ...data, outcome: 'recommended' }, arrival, '', [link]))
})
