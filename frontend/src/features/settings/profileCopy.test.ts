import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Profile } from '../../lib/api.ts'
import { connectedNotice, deleteConsequences, pinCaption } from './profileCopy.ts'

const me: Profile = { id: 1, name: 'Me', avatar: 'avatar-01', has_pin: false, is_manager: true, position: 0 }
const ana: Profile = { id: 7, name: 'Ana', avatar: 'avatar-02', has_pin: true, is_manager: false, position: 1 }

test('deleting a profile names everything that goes with it', () => {
  assert.deepEqual(deleteConsequences(ana), [
    "Ana's list accounts are disconnected from this server",
    "Ana's reading positions, bookmarks and history are deleted",
    'Series only Ana follows are removed from the server; series someone else follows stay',
  ])
})

test('coming back from a sign-in names whose account it was', () => {
  const profiles = [me, ana]
  assert.equal(
    connectedNotice(new URLSearchParams('connected=anilist&profile=7'), profiles),
    'AniList connected for Ana',
  )
  assert.equal(
    connectedNotice(new URLSearchParams('connected=mal&profile=1'), profiles),
    'MyAnimeList connected',
  )
  assert.equal(
    connectedNotice(new URLSearchParams('connected=anilist&profile=999'), profiles),
    'AniList connected',
  )
  assert.equal(connectedNotice(new URLSearchParams('connected=anilist'), profiles), 'AniList connected')
  assert.equal(connectedNotice(new URLSearchParams(''), profiles), null)
})

test('the pin caption says whether one is set', () => {
  assert.equal(pinCaption(ana), 'PIN set')
  assert.equal(pinCaption(me), 'No PIN')
})
