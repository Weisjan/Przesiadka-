import assert from 'node:assert/strict'
import test from 'node:test'
import { readWalking } from '../src/walkingData.ts'

const pair = '["skm:7500","ztm:2001"]'
const response = () => ({ status: 'available', from_stop_id: 'skm:7500', to_stop_id: 'ztm:2001', estimate: {
  status: 'available', source: 'openrouteservice', confidence: 'estimated', walking_seconds: 241.2, walking_minutes: 5, distance_m: 321.4,
  calculated_at: '2026-11-12T12:00:00+00:00', expires_at: '2026-12-12T12:00:00+00:00', attribution: 'ORS / HeiGIT / OSM',
  license: 'CC-BY-SA-4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0/', terms_url: 'https://account.heigit.org/info/tos', rounding: 'ceil_to_full_minutes',
} })

test('incorrect source, verified claims, invalid metrics and wrong pairs are rejected', () => {
  for (const change of [{ confidence: 'verified' }, { walking_minutes: 0 }, { walking_seconds: Infinity }, { license: 'unknown' }, { distance_m: -1 }]) {
    const data = response(); Object.assign(data.estimate, change)
    assert.throws(() => readWalking(data, 'skm:7500', 'ztm:2001'))
  }
  assert.throws(() => readWalking(response(), 'ztm:2001', 'skm:7500'))
})
