import assert from 'node:assert/strict'
import test from 'node:test'
import { fromIso, timeHints, eventClock } from '../src/dates.ts'
import { readEvaluation } from '../src/types.ts'

test('Warsaw dates preserve midnight and repeated DST offsets', () => {
 assert.equal(fromIso('2026-11-13T23:30:00+00:00').date,'2026-11-14')
 const first='2026-10-25T02:30:00+02:00', second='2026-10-25T02:30:00+01:00'
 assert.ok(timeHints(first,second,[first,second]).includes('UTC+02:00'))
 assert.ok(timeHints(second,first,[first,second]).includes('UTC+01:00'))
 assert.ok(timeHints('2026-11-14T00:05:00+01:00','2026-11-13T23:58:00+01:00',[]).includes('następnego dnia'))
})
test('close real courses remain distinguishable',()=>{
 const times=['2026-11-13T17:42:00+01:00','2026-11-13T17:42:30+01:00']
 assert.notEqual(eventClock(times[0],times),eventClock(times[1],times))
})
test('invalid evaluation never becomes a displayed status',()=>{
 assert.throws(()=>readEvaluation({status:'maybe',margin_minutes:Infinity}))
})
