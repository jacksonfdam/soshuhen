import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Profile } from './api.ts'
import {
  AVATAR_KEYS,
  avatarUrl,
  profileHeaders,
  profilePatch,
  reorder,
  validName,
  validPin,
} from './profiles.ts'

function p(id: number, position: number): Profile {
  return { id, name: `P${id}`, avatar: 'avatar-01', has_pin: false, is_manager: id === 1, position }
}

test('there are twelve avatars', () => {
  assert.equal(AVATAR_KEYS.length, 12)
  assert.equal(AVATAR_KEYS[0], 'avatar-01')
  assert.equal(AVATAR_KEYS[11], 'avatar-12')
})

test('a pin is four to six digits', () => {
  for (const ok of ['1234', '123456']) assert.equal(validPin(ok), true)
  for (const bad of ['', '123', '1234567', '12a4']) assert.equal(validPin(bad), false)
})

test('an empty pin field keeps the pin; clearing is explicit', () => {
  const before: Profile = {
    id: 2,
    name: 'Ana',
    avatar: 'avatar-02',
    has_pin: true,
    is_manager: false,
    position: 1,
  }
  assert.equal(profilePatch(before, { name: 'Ana', avatar: 'avatar-02', pin: '', clearPin: false }), null)
  assert.deepEqual(
    profilePatch(before, { name: 'Ana', avatar: 'avatar-02', pin: '', clearPin: true }),
    { pin: null },
  )
  assert.deepEqual(
    profilePatch(before, { name: 'Bia', avatar: 'avatar-05', pin: '4321', clearPin: false }),
    { name: 'Bia', avatar: 'avatar-05', pin: '4321' },
  )
})

test('moving past either end changes nothing', () => {
  const list = [p(1, 0), p(2, 1), p(3, 2)]
  assert.deepEqual(reorder(list, 1, -1), [])
  assert.deepEqual(reorder(list, 3, 1), [])
  assert.deepEqual(reorder(list, 2, -1), [
    { id: 2, position: 0 },
    { id: 1, position: 1 },
  ])
})

test('an unknown avatar key falls back to the first', () => {
  assert.equal(avatarUrl('avatar-07'), '/avatars/avatar-07.svg')
  assert.equal(avatarUrl('nope'), '/avatars/avatar-01.svg')
})

test('the profile header is sent only when a profile is named', () => {
  assert.deepEqual(profileHeaders(), { 'Content-Type': 'application/json' })
  assert.deepEqual(profileHeaders(7), {
    'Content-Type': 'application/json',
    'X-Soshuhen-Profile': '7',
  })
})

test('a name is trimmed and 1 to 40 characters', () => {
  assert.equal(validName('  '), false)
  assert.equal(validName('x'.repeat(41)), false)
  assert.equal(validName(' Ana '), true)
})

test('reordering with gaps keeps everyone else in place', () => {
  // Positions left by deleted profiles: M 0, A 3, B 4, C 5. Moving C up must
  // give M, A, C, B, not drop A to the bottom.
  const list = [p(1, 0), p(2, 3), p(3, 4), p(4, 5)]
  assert.deepEqual(reorder(list, 4, -1), [
    { id: 2, position: 1 },
    { id: 4, position: 2 },
    { id: 3, position: 3 },
  ])
})
