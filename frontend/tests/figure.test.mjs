import assert from 'node:assert/strict'
import test from 'node:test'
import { figureState } from '../src/formatting.ts'

test('figure uses the exact backend margin including the two-minute boundary', () => {
  for (const [margin, state] of [[-1, 'missed'], [0, 'edge'], [1.99, 'edge'], [2, 'success'], [5, 'success'], [null, 'idle'], [NaN, 'idle']]) {
    assert.equal(figureState(margin), state)
  }
})
