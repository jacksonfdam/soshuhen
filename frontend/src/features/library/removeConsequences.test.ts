import assert from 'node:assert/strict'
import { test } from 'node:test'

import { removeConsequences } from './removeConsequences.ts'

const ALWAYS = [
  'Chapters already downloaded stay on disk and in Komga.',
  'A list sync will not bring them back to your library.',
  'Your MyAnimeList and AniList entries are left as they are.',
]

test('series only you follow are removed and their queue cancelled', () => {
  assert.deepEqual(removeConsequences([{ held_by: [1] }, { held_by: [] }], 1), [
    'Anything queued for them is cancelled.',
    ...ALWAYS,
  ])
})

test('a shared series leaves only your library', () => {
  assert.deepEqual(removeConsequences([{ held_by: [1, 7] }], 1), [
    '1 series someone else also follows leaves your library only; it stays on the server for them.',
    ...ALWAYS,
  ])
})

test("a series only someone else follows is left alone", () => {
  assert.deepEqual(removeConsequences([{ held_by: [7] }, { held_by: [1] }], 1), [
    'Anything queued for them is cancelled.',
    "1 series is only on someone else's lists and will be left alone.",
    ...ALWAYS,
  ])
})

test('without the profile list nothing is claimed about who follows what', () => {
  assert.deepEqual(removeConsequences([{ held_by: [7] }], null), [
    'Anything queued for them is cancelled.',
    ...ALWAYS,
  ])
})
