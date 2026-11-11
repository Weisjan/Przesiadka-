import assert from 'node:assert/strict'
import test from 'node:test'
import { demoExamples } from '../src/demoExamples.ts'
import { fromIso, toIso } from '../src/dates.ts'

test('three named examples contain only analysis inputs, without database identifiers', () => {
  assert.deepEqual(demoExamples.map(example => example.scenario.name), [
    'Spokojna przesiadka', 'Przesiadka na styk', 'Ostatni kurs',
  ])
  assert.equal(new Set(demoExamples.map(example => example.key)).size, 3)
  for (const example of demoExamples) {
    assert.ok(example.description)
    assert.equal('id' in example.scenario, false)
    assert.deepEqual(Object.keys(example.scenario).sort(), [
      'name', 'interchange', 'arrival_line', 'departure_line', 'direction',
      'arrival_at', 'departure_at', 'walking_minutes', 'next_departures',
    ].sort())
  }
})

test('example dates are fixed Warsaw dates and survive the existing date conversion', () => {
  for (const { scenario } of demoExamples) {
    for (const date of [scenario.arrival_at, scenario.departure_at, ...scenario.next_departures]) {
      assert.match(date, /^2026-11-(10|11)T\d{2}:\d{2}:00\+01:00$/)
      assert.equal(toIso(fromIso(date)), date)
    }
  }
  const calm = demoExamples[0].scenario
  assert.equal(calm.arrival_at, '2026-11-10T17:42:00+01:00')
  assert.equal(calm.departure_at, '2026-11-10T17:51:00+01:00')
  assert.equal(calm.walking_minutes, 3)
  assert.deepEqual(calm.next_departures, ['2026-11-10T18:03:00+01:00'])
})

test('last course crosses midnight and has no supplied later departures', () => {
  const last = demoExamples[2].scenario
  assert.equal(last.arrival_at, '2026-11-10T23:58:00+01:00')
  assert.equal(last.departure_at, '2026-11-11T00:04:00+01:00')
  assert.deepEqual(last.next_departures, [])
})
