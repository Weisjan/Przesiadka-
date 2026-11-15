import assert from 'node:assert/strict'
import test from 'node:test'
import { readAvailability } from '../src/demoData.ts'

const sources = [
  { imported: true, service_start_date: '2026-10-19', service_end_date: '2026-12-12' },
  { imported: true, service_start_date: '2026-11-11', service_end_date: '2026-11-25' },
]
const group = operator => ({ name: 'Fixture', operator, stops: [{ stop_id: `${operator}:fixture`, stop_name: 'Fixture', operator }] })
const demo = { enabled: true, label: 'Historical fixture', departure_date: '2026-11-13', min_departure_time: '16:00', max_departure_time: '18:00', walking_reference_at: '2026-11-12T12:00:00+00:00',
  examples: [{ id: 'fixture', name: 'Fixture', description: 'Synthetic data', departure_date: '2026-11-13', departure_time: '17:00', origin: group('skm'), destination: group('ztm') }] }

test('normal availability uses the common date bounds without inventing demo examples', () => {
  assert.deepEqual(readAvailability({ is_realtime: false, sources }), { first: '2026-11-11', last: '2026-11-25', demo: null })
})
test('demo configuration supplies only real API input fields, with historical date bounds', () => {
  const result = readAvailability({ is_realtime: false, sources, demo })
  assert.equal(result.first, '2026-11-13')
  assert.equal(result.demo.examples[0].origin.stops[0].stop_id, 'skm:fixture')
  assert.equal('evaluation' in result.demo.examples[0], false)
})
test('invalid sources, operators and dates do not become clickable examples', () => {
  assert.throws(() => readAvailability({ sources, is_realtime: true }))
  assert.throws(() => readAvailability({ sources: [], is_realtime: false }))
  assert.throws(() => readAvailability({ sources, is_realtime: false, demo: { ...demo, examples: [{ ...demo.examples[0], destination: group('skm') }] } }))
  assert.throws(() => readAvailability({ sources, is_realtime: false, demo: { ...demo, examples: [] } }))
  assert.throws(() => readAvailability({ sources: [null, sources[1]], is_realtime: false }))
  assert.throws(() => readAvailability({ sources, is_realtime: false, demo: { ...demo, examples: [{ ...demo.examples[0], departure_time: '25:00' }] } }))
})
