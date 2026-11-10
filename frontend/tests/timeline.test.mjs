import assert from 'node:assert/strict'
import test from 'node:test'
import { timelineEvents, markerLanes, durationParts } from '../src/timeline.ts'
import { eventClock, timeHints } from '../src/dates.ts'

const scenario = { arrival_at: '2026-11-10T17:42:00+01:00', departure_at: '2026-11-10T17:51:00+01:00' }
const result = { expected_stop_arrival_at: scenario.departure_at, plan_b_departure_at: null }

test('exactly simultaneous arrival at stop and departure form one point with both meanings', () => {
  const events = timelineEvents(scenario, result)
  assert.equal(events.length, 2)
  assert.equal(events[1].label, 'dotarcie i odjazd')
  assert.deepEqual(events[1].kinds, ['departure', 'ready'])
  assert.match(events[1].description, /Planowany odjazd/)
  assert.match(events[1].description, /Oczekiwane dotarcie na przystanek/)
  assert.equal(events[1].date, scenario.departure_at)
})

test('all coincident meanings and equivalent fractional representations are retained', () => {
  const events = timelineEvents({ ...scenario, arrival_at: scenario.departure_at }, { ...result, expected_stop_arrival_at: '2026-11-10T17:51:00.000000+01:00' })
  assert.equal(events.length, 1)
  assert.equal(events[0].label, 'przyjazd, dotarcie i odjazd')
  assert.equal(events[0].kinds.length, 3)
})

test('nearby instants, including one microsecond apart, are not merged or moved', () => {
  for (const ready of ['2026-11-10T17:51:01+01:00', '2026-11-10T17:51:00.000001+01:00']) {
    const events = timelineEvents(scenario, { ...result, expected_stop_arrival_at: ready })
    assert.equal(events.length, 3)
    assert.equal(events[2].date, ready)
  }
  assert.deepEqual(markerLanes([10, 10.001, 10.002, 80], 800), [0, 1, 2, 0])
  assert.deepEqual(markerLanes([10, 20, 30], 800), [0, 0, 0])
})

test('midnight merges only identical instants and immediately indicates the next day', () => {
  const departure = '2026-11-11T00:07:00+01:00'
  const data = { arrival_at: '2026-11-10T23:58:00+01:00', departure_at: departure }
  const events = timelineEvents(data, { ...result, expected_stop_arrival_at: departure })
  assert.equal(events.length, 2)
  assert.deepEqual(timeHints(departure, data.arrival_at, events.map(event => event.date)), ['następnego dnia'])
})

test('fall repeated wall-clock hours remain distinct and both offsets are visible', () => {
  const first = '2026-10-25T02:30:00+02:00'
  const second = '2026-10-25T02:30:00+01:00'
  const events = timelineEvents({ arrival_at: first, departure_at: second }, null)
  assert.equal(events.length, 2)
  assert.deepEqual(timeHints(first, first, [first, second]), ['UTC+02:00'])
  assert.deepEqual(timeHints(second, first, [first, second]), ['UTC+01:00'])
  assert.equal(eventClock(first, [first, second]), '02:30')
})

test('spring offset changes and day differences use the Warsaw calendar, not elapsed 24h', () => {
  const first = '2026-03-29T01:58:00+01:00'
  const second = '2026-03-29T03:07:00+02:00'
  assert.deepEqual(timeHints(first, first, [first, second]), ['UTC+01:00'])
  assert.deepEqual(timeHints(second, first, [first, second]), ['UTC+02:00'])
  assert.deepEqual(timeHints('2026-03-30T00:01:00+02:00', first, []), ['następnego dnia'])
})

test('close events expose seconds and microseconds instead of identical minute labels', () => {
  const first = scenario.departure_at
  const second = '2026-11-10T17:51:01+01:00'
  const microsecond = '2026-11-10T17:51:00.000001+01:00'
  assert.equal(eventClock(first, [first, second]), '17:51:00')
  assert.equal(eventClock(second, [first, second]), '17:51:01')
  assert.equal(eventClock(microsecond, [first, microsecond]), '17:51:00,000001')
  assert.deepEqual(timeHints(first, first, [first]), [])
})

test('nonzero sub-minute margins and thresholds never display as zero minutes', () => {
  assert.deepEqual(durationParts(1 / 60000000), { amount: '0,000001', unit: 's' })
  assert.deepEqual(durationParts(-1 / 60000000), { amount: '-0,000001', unit: 's' })
  assert.deepEqual(durationParts(0.5), { amount: '30', unit: 's' })
  assert.deepEqual(durationParts(0), { amount: '0', unit: 'min' })
  assert.deepEqual(durationParts(6), { amount: '6', unit: 'min' })
})
