import assert from 'node:assert/strict'
import test from 'node:test'
import { applyWalkingEstimate, readWalking, selectWalkingPair } from '../src/walkingData.ts'

const pair = '["skm:7500","ztm:2001"]'
const response = () => ({ status: 'available', from_stop_id: 'skm:7500', to_stop_id: 'ztm:2001', estimate: {
  status: 'available', source: 'openrouteservice', confidence: 'estimated', walking_seconds: 241.2, walking_minutes: 5, distance_m: 321.4,
  calculated_at: '2026-11-12T12:00:00+00:00', expires_at: '2026-12-12T12:00:00+00:00', attribution: 'ORS / HeiGIT / OSM',
  license: 'CC-BY-SA-4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0/', terms_url: 'https://account.heigit.org/info/tos', rounding: 'ceil_to_full_minutes',
} })

test('a stored estimate fills the walking field using backend minutes', () => {
  const state = selectWalkingPair({ pair: '', value: '', manual: false }, pair)
  assert.equal(applyWalkingEstimate(state, pair, readWalking(response(), 'skm:7500', 'ztm:2001')).value, '5')
})

test('manual input before and during a fetch cannot be overwritten by its response', () => {
  const edited = selectWalkingPair({ pair: '', value: '7', manual: true }, pair)
  assert.equal(applyWalkingEstimate(edited, pair, response()), edited)
  const duringFetch = { pair, value: '9', manual: true }
  assert.equal(applyWalkingEstimate(duringFetch, pair, response()), duringFetch)
})

test('a changed directional pair clears old input and ignores stale responses', () => {
  const changed = selectWalkingPair({ pair, value: '7', manual: true }, 'reverse')
  assert.deepEqual(changed, { pair: 'reverse', value: '', manual: false })
  assert.equal(applyWalkingEstimate(changed, pair, response()), changed)
})

test('missing, stale and no-route results cannot fill zero minutes', () => {
  const state = { pair, value: '', manual: false }
  for (const status of ['missing', 'stale', 'no_route']) assert.equal(applyWalkingEstimate(state, pair, { ...response(), status }), state)
  assert.equal(readWalking({ status: 'missing', from_stop_id: 'skm:7500', to_stop_id: 'ztm:2001', estimate: null }, 'skm:7500', 'ztm:2001').status, 'missing')
  const data = response(); data.status = 'no_route'; data.estimate.status = 'no_route'
  data.estimate.distance_m = data.estimate.walking_seconds = data.estimate.walking_minutes = null
  assert.equal(readWalking(data, 'skm:7500', 'ztm:2001').status, 'no_route')
})

test('incorrect source, verified claims, invalid metrics and wrong pairs are rejected', () => {
  for (const change of [{ confidence: 'verified' }, { walking_minutes: 0 }, { walking_seconds: Infinity }, { license: 'unknown' }, { distance_m: -1 }]) {
    const data = response(); Object.assign(data.estimate, change)
    assert.throws(() => readWalking(data, 'skm:7500', 'ztm:2001'))
  }
  assert.throws(() => readWalking(response(), 'ztm:2001', 'skm:7500'))
})

test('a later stale or missing result clears an automatic value but preserves a manual correction', () => {
  const automatic = { pair, value: '5', manual: false }
  const manual = { ...automatic, value: '7', manual: true }
  for (const status of ['missing', 'stale', 'no_route']) {
    assert.equal(applyWalkingEstimate(automatic, pair, { ...response(), status }).value, '')
    assert.equal(applyWalkingEstimate(manual, pair, { ...response(), status }), manual)
  }
})
