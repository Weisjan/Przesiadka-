import assert from 'node:assert/strict'
import test from 'node:test'
import { dateTimeOptions, fromIso, toIso } from '../src/dates.ts'
import { readEvaluation } from '../src/types.ts'

const local = (date, time, offset = '') => ({ date, time, offset })

test('winter and summer use Warsaw offsets independently of the machine zone', () => {
  const previous = process.env.TZ
  try {
    for (const zone of ['UTC', 'America/Los_Angeles', 'Asia/Tokyo']) {
      process.env.TZ = zone
      assert.equal(toIso(local('2026-11-10', '17:42')), '2026-11-10T17:42:00+01:00')
      assert.equal(toIso(local('2026-07-10', '17:42')), '2026-07-10T17:42:00+02:00')
    }
  } finally {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  }
})

test('spring gap is rejected and valid times on either side round-trip', () => {
  assert.deepEqual(dateTimeOptions(local('2026-03-29', '02:30')), [])
  assert.throws(() => toIso(local('2026-03-29', '02:30')), /nie istnieje/)
  assert.equal(toIso(local('2026-03-29', '01:58')), '2026-03-29T01:58:00+01:00')
  assert.equal(toIso(local('2026-03-29', '03:07')), '2026-03-29T03:07:00+02:00')
})

test('fall overlap requires an explicit choice and orders both occurrences by instant', () => {
  const value = local('2026-10-25', '02:30')
  assert.deepEqual(dateTimeOptions(value), ['2026-10-25T02:30:00+02:00', '2026-10-25T02:30:00+01:00'])
  assert.throws(() => toIso(value), /dwa razy/)
  assert.equal(toIso({ ...value, offset: '+02:00' }), '2026-10-25T02:30:00+02:00')
  assert.equal(toIso({ ...value, offset: '+01:00' }), '2026-10-25T02:30:00+01:00')
})

test('midnight retains distinct dates', () => {
  const arrival = toIso(local('2026-11-10', '23:58'))
  const departure = toIso(local('2026-11-11', '00:07'))
  assert.equal(Date.parse(departure) - Date.parse(arrival), 9 * 60000)
})

test('editing existing times retains both fall offsets and sub-minute precision', () => {
  for (const iso of ['2026-10-25T02:30:00+02:00', '2026-10-25T02:30:00+01:00', '2026-11-10T17:42:36.123456+01:00']) {
    assert.equal(toIso(fromIso(iso)), iso)
  }
  assert.equal(toIso({ ...fromIso('2026-11-10T17:42:36+01:00'), time: '17:43' }), '2026-11-10T17:43:00+01:00')
})

test('missing and invalid calendar input cannot become a different date', () => {
  for (const value of [local('', ''), local('2026-02-30', '12:00'), local('2026-11-10', '25:00')]) {
    assert.throws(() => toIso(value))
  }
})

test('malformed API results are rejected before selecting a face', () => {
  const result = { margin_minutes: 6, delay_threshold_minutes: 6, status: 'Zdążysz', has_safe_margin: true,
    expected_stop_arrival_at: '2026-11-10T17:45:00+01:00', plan_b_status: 'not_needed', plan_b_departure_at: null }
  assert.deepEqual(readEvaluation(result), result)
  for (const change of [{ status: 'maybe' }, { margin_minutes: Infinity }, { plan_b_status: 'available' }, { expected_stop_arrival_at: 'bad' }, { has_safe_margin: 'true' }]) {
    assert.throws(() => readEvaluation({ ...result, ...change }))
  }
})
