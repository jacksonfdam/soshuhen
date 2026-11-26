import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Profile } from '../../lib/api.ts'
import { holdersOf } from './holders.ts'

const me: Profile = { id: 1, name: 'Me', avatar: 'avatar-01', has_pin: false, is_manager: true, position: 0 }
const ana: Profile = { id: 7, name: 'Ana', avatar: 'avatar-02', has_pin: false, is_manager: false, position: 1 }

test('a series on the manager\'s lists shows no chip', () => {
  assert.equal(holdersOf({ held_by: [1, 7] }, [me, ana]), null)
})

test('a series no list holds shows no chip', () => {
  assert.equal(holdersOf({ held_by: [] }, [me, ana]), null)
})

test('a series only someone else follows names them', () => {
  assert.deepEqual(holdersOf({ held_by: [7] }, [me, ana]), [ana])
})

test('without the profile list nothing is claimed', () => {
  assert.equal(holdersOf({ held_by: [7] }, null), null)
})
