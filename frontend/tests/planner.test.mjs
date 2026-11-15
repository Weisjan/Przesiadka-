import assert from 'node:assert/strict'
import test from 'node:test'
import { planIdentity, readPlan, readPlannedEvaluation, readStopGroups } from '../src/plannerData.ts'

const input = { origin_stop_ids: ['skm:origin'], destination_stop_ids: ['ztm:goal'], departure_date: '2026-11-13', departure_time: '17:00', max_results: 3 }
const event = (operator, stop, sequence, clock) => ({ operator, operator_name: 'Fixture', stop_id: `${operator}:${stop}`, stop_name: stop,
  route_id: `${operator}:route`, trip_id: `${operator}:trip`, service_id: `${operator}:service`, service_date: input.departure_date,
  line: '1', route_type: 2, direction: 'Fixture', direction_id: 0, stop_sequence: sequence, pickup_type: 0, drop_off_type: 0,
  arrival_at: `2026-11-13T${clock}:00+01:00`, departure_at: `2026-11-13T${clock}:00+01:00` })
function response() {
  const origin = event('skm', 'origin', 1, '17:10'), arrival = event('skm', 'transfer', 2, '17:20')
  const departure = event('ztm', 'boarding', 3, '17:25'), destination = event('ztm', 'goal', 4, '17:40')
  const walking = { status: 'available', from_stop_id: arrival.stop_id, to_stop_id: departure.stop_id, estimate: {
    status: 'available', source: 'openrouteservice', confidence: 'estimated', walking_seconds: 180, walking_minutes: 3, distance_m: 200,
    calculated_at: '2026-11-13T00:00:00+01:00', expires_at: '2026-12-13T00:00:00+01:00', attribution: 'Synthetic fixture',
    license: 'CC-BY-SA-4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0/', terms_url: 'https://account.heigit.org/info/tos', rounding: 'ceil_to_full_minutes' } }
  return { is_realtime: false, schedule_status: 'planned', outcome: 'found', ...input, requested_departure_at: '2026-11-13T17:00:00+01:00',
    results: [{ origin, arrival, departure, destination, link: { id: 'fixture', approval_status: 'approved', arrival_stop: arrival, departure_stop: departure, walking, walking_minutes: 3 },
      evaluation: { margin_minutes: 2, delay_threshold_minutes: 2, status: 'Zdążysz', has_safe_margin: true, expected_stop_arrival_at: '2026-11-13T17:23:00+01:00' },
      total_minutes: 30, elapsed_from_request_minutes: 40, initial_wait_minutes: 10, waiting_minutes: 2, risk: 'estimated' }],
    scope: { approved_links: 1, available_links: 1 }, sources: ['skm', 'ztm'].map(operator => ({ operator, imported: true, attribution: 'Fixture',
      documentation_url: 'https://example.invalid', sha256: '0'.repeat(64), imported_at: '2026-11-13T00:00:00+01:00', service_start_date: '2026-01-01', service_end_date: '2026-12-31' })),
    reason: 'Fixture', limitations: ['Only approved links.'], has_more: false }
}

test('planner accepts an exact, chronological local itinerary and retains identities', () => {
  const data = response()
  assert.equal(readPlan(data, input), data)
  assert.notEqual(planIdentity(data.results[0]), planIdentity({ ...data.results[0], arrival: { ...data.results[0].arrival, stop_sequence: 5 } }))
})

test('planner rejects responses belonging to an old origin, destination, date or time', () => {
  for (const change of [{ origin_stop_ids: ['skm:other'] }, { destination_stop_ids: ['ztm:other'] }, { departure_date: '2026-11-14' }, { departure_time: '18:00' }]) {
    assert.throws(() => readPlan(response(), { ...input, ...change }))
  }
})

test('planner rejects trip, occurrence, temporal, walking and provenance mismatches', () => {
  for (const modify of [x => { x.arrival.trip_id = 'skm:other' }, x => { x.destination.route_id = 'ztm:other' },
    x => { x.destination.stop_sequence = 1 }, x => { x.origin.departure_at = '2026-11-13T18:00:00+01:00' },
    x => { x.link.approval_status = 'unapproved' }, x => { x.link.walking.status = 'stale' }, x => { x.total_minutes = Infinity }]) {
    const data = response(); modify(data.results[0]); assert.throws(() => readPlan(data, input))
  }
  const data = response(); data.is_realtime = true; assert.throws(() => readPlan(data, input))
})

test('empty plans have explicit outcomes and no invented course', () => {
  const data = { ...response(), outcome: 'no_transfer_link', results: [] }
  assert.equal(readPlan(data, input).results.length, 0)
  assert.throws(() => readPlan({ ...data, outcome: 'found' }, input))
})

test('simulation rejects a reimport even when interchange times stay unchanged', () => {
  const data = response(), plan = data.results[0]
  const value = { is_realtime: false, schedule_status: 'planned', arrival: plan.arrival, link: plan.link,
    results: [{ departure: plan.departure, evaluation: plan.evaluation }], sources: data.sources,
    search_window: { start_at: plan.arrival.arrival_at, end_at_exclusive: '2026-11-13T23:00:00+01:00' }, limitations: [] }
  assert.equal(readPlannedEvaluation(value, plan, data.sources), value)
  assert.throws(() => readPlannedEvaluation({ ...value, sources: data.sources.map(s => ({ ...s, sha256: '1'.repeat(64) })) }, plan, data.sources))
})

test('stop lookup keeps exact operator IDs and rejects invalid groups', () => {
  const data = { is_realtime: false, groups: [{ name: 'Goal', operator: 'ztm', stops: [{ operator: 'ztm', stop_id: 'ztm:1', stop_name: 'Goal 01' }, { operator: 'ztm', stop_id: 'ztm:2', stop_name: 'Goal 02' }] }], has_more: false }
  assert.equal(readStopGroups(data, 'ztm').groups[0].stops.length, 2)
  assert.throws(() => readStopGroups(data, 'skm'))
  assert.throws(() => readStopGroups({ ...data, is_realtime: true }, 'ztm'))
})
