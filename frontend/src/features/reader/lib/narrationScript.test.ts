import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  CHAPTER_END,
  UNREADABLE,
  failureScript,
  narrationDirection,
  pageScript,
  type ScriptItem,
} from './narrationScript.ts'

const block = (text: string) => ({ box: [0, 0, 1, 1], text })

/** A transcript with one panel per argument, each holding the given lines. */
const transcript = (...panels: string[][]) => ({
  engine: 'fake',
  language: 'en',
  width: 1,
  height: 1,
  panels: panels.map((lines) => ({ box: [0, 0, 1, 1], blocks: lines.map(block) })),
})

const said = (items: ScriptItem[]) => items.map((item) => item.text)

test('a page is its number, then each panel and its blocks', () => {
  assert.deepEqual(
    said(pageScript(4, transcript(['Good morning.', 'Where are you going?'], ['Wait!']))),
    ['Page 5.', 'Panel 1.', 'Good morning.', 'Where are you going?', 'Panel 2.', 'Wait!'],
  )
})

test('a wordless panel is announced as such', () => {
  assert.deepEqual(said(pageScript(0, transcript(['Hello.'], []))), [
    'Page 1.',
    'Panel 1.',
    'Hello.',
    'Panel 2.',
    'No text.',
  ])
})

test('a single panel is not announced', () => {
  assert.deepEqual(said(pageScript(2, transcript(['First.', 'Second.']))), [
    'Page 3.',
    'First.',
    'Second.',
  ])
})

test('a page with no text still says its number', () => {
  assert.deepEqual(said(pageScript(0, transcript([]))), ['Page 1.', 'No text.'])
  assert.deepEqual(said(pageScript(0, transcript())), ['Page 1.', 'No text.'])
})

test('a page of several panels with no text in any says so once', () => {
  assert.deepEqual(said(pageScript(0, transcript([], [], []))), ['Page 1.', 'No text.'])
})

test('a block of nothing but spaces is not spoken', () => {
  assert.deepEqual(said(pageScript(0, transcript(['  ', 'Real.']))), ['Page 1.', 'Real.'])
})

test('each item knows what on the page it is', () => {
  const items = pageScript(4, transcript(['A.'], ['B.']))
  assert.deepEqual(
    items.map(({ page, panel, block: index }) => [page, panel, index]),
    [
      [4, null, null],
      [4, 0, null],
      [4, 0, 0],
      [4, 1, null],
      [4, 1, 0],
    ],
  )
})

test('a block keeps its own index when one before it was left out', () => {
  const items = pageScript(0, transcript(['  ', 'Real.']))
  assert.deepEqual(items.at(-1), { text: 'Real.', page: 0, panel: 0, block: 1 })
})

test('a page that could not be read says so, after its number', () => {
  assert.deepEqual(said(failureScript(6)), ['Page 7.', UNREADABLE])
  assert.deepEqual(
    failureScript(6).map(({ page }) => page),
    [6, 6],
  )
})

test('the fixed sentences are the ones the interface promises', () => {
  assert.equal(UNREADABLE, 'This page could not be read aloud.')
  assert.equal(CHAPTER_END, 'End of chapter.')
})

test('only the right-to-left paged mode reads right to left', () => {
  assert.equal(narrationDirection('paged_rtl'), 'rtl')
  for (const mode of ['paged_ltr', 'double', 'long_strip'] as const) {
    assert.equal(narrationDirection(mode), 'ltr')
  }
})
