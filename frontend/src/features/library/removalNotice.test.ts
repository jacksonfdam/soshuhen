import assert from 'node:assert/strict'
import { test } from 'node:test'

import { removalNotice } from './removalNotice.ts'

test('series deleted outright', () => {
  assert.equal(
    removalNotice({ removed: 2, deleted: 1, skipped: [] }),
    'Removed 2 series from your library. A list sync will not bring them back.',
  )
})

test('a series someone else still follows stays for them', () => {
  assert.equal(
    removalNotice({ removed: 1, deleted: 0, skipped: [] }),
    'Removed 1 series from your library. Someone else still follows it, so it stays on the server for them.',
  )
})

test('a series only someone else follows is left alone', () => {
  assert.equal(
    removalNotice({ removed: 0, deleted: 0, skipped: [5] }),
    "Nothing removed: 1 series is only on someone else's lists. Remove it from their profile instead.",
  )
})

test('a mixed selection names both', () => {
  assert.equal(
    removalNotice({ removed: 2, deleted: 2, skipped: [9] }),
    "Removed 2 series from your library. A list sync will not bring them back. 1 more is only on someone else's lists and was left alone.",
  )
})
