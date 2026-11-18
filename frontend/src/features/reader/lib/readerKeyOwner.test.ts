import assert from 'node:assert/strict'
import { test } from 'node:test'

import { keptByControl } from './readerKeyOwner.ts'

test('a text field keeps every key', () => {
  assert.equal(keptByControl('INPUT', 'text', ' '), true)
  assert.equal(keptByControl('INPUT', null, 'n'), true)
  assert.equal(keptByControl('TEXTAREA', null, 'ArrowLeft'), true)
})

test('the page slider keeps none, so the arrows still turn pages from it', () => {
  assert.equal(keptByControl('INPUT', 'range', 'ArrowLeft'), false)
  assert.equal(keptByControl('INPUT', 'range', ' '), false)
})

test('a select keeps every key: arrows and letters choose its options', () => {
  assert.equal(keptByControl('SELECT', null, 'ArrowRight'), true)
  assert.equal(keptByControl('SELECT', null, 'n'), true)
  assert.equal(keptByControl('SELECT', null, ' '), true)
})

test('a button keeps the keys that press it, and only those', () => {
  assert.equal(keptByControl('BUTTON', 'button', ' '), true)
  assert.equal(keptByControl('BUTTON', 'button', 'Enter'), true)
  assert.equal(keptByControl('BUTTON', 'button', 'ArrowLeft'), false)
  assert.equal(keptByControl('BUTTON', 'button', 'n'), false)
  assert.equal(keptByControl('BUTTON', 'button', 'Escape'), false)
})

test('a link keeps Enter, which follows it, and not the space bar, which does not', () => {
  assert.equal(keptByControl('A', null, 'Enter'), true)
  assert.equal(keptByControl('A', null, ' '), false)
})

test('the page itself keeps nothing', () => {
  assert.equal(keptByControl('MAIN', null, ' '), false)
  assert.equal(keptByControl('BODY', null, 'n'), false)
  assert.equal(keptByControl('DIV', null, 'ArrowRight'), false)
})
