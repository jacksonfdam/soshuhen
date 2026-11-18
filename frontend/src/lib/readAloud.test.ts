import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  LONGEST_UTTERANCE,
  ReadAloudPlayer,
  firstUnread,
  utterances,
  type PlayState,
  type SpeechEngine,
  type SpeechSettings,
} from './readAloud.ts'

/** Stands in for `speechSynthesis`: remembers what it was asked to say and
    finishes an utterance only when the test says so. */
function fakeEngine() {
  const spoken: { text: string; settings: SpeechSettings }[] = []
  const pending: ((finished: boolean) => void)[] = []
  let cancels = 0
  const engine: SpeechEngine = {
    voices: () => [],
    onVoicesChanged: () => () => {},
    speak(text, settings, done) {
      spoken.push({ text, settings })
      pending.push(done)
    },
    cancel() {
      cancels += 1
      // The browser reports a cancelled utterance as an error, late.
      for (const done of pending.splice(0)) queueMicrotask(() => done(false))
    },
  }
  return {
    engine,
    spoken,
    get cancels() {
      return cancels
    },
    finish() {
      const done = pending.shift()
      assert.ok(done, 'nothing is being spoken')
      done(true)
    },
  }
}

function player(blocks: string[][], from = 0) {
  const fake = fakeEngine()
  const shown: (number | null)[] = []
  const states: PlayState[] = []
  const reader = new ReadAloudPlayer(
    fake.engine,
    { block: (index) => shown.push(index), state: (state) => states.push(state) },
    { voice: null, rate: 1 },
  )
  reader.start(blocks, from)
  return { fake, reader, shown, states }
}

const settle = () => new Promise((done) => setTimeout(done, 0))

test('a short paragraph is one utterance', () => {
  assert.deepEqual(utterances('  She   said\nhello.  '), ['She said hello.'])
})

test('an empty paragraph says nothing', () => {
  assert.deepEqual(utterances(' \n '), [])
})

test('a long paragraph is split by sentence, and short sentences are joined', () => {
  const sentence = 'This is a sentence of about sixty characters, give or take.'
  const paragraph = Array.from({ length: 8 }, () => sentence).join(' ')
  const parts = utterances(paragraph)
  assert.ok(parts.length > 1)
  for (const part of parts) assert.ok(part.length <= LONGEST_UTTERANCE, part)
  // Three of them fit in one utterance; nothing is lost or reordered.
  assert.equal(parts[0], [sentence, sentence, sentence].join(' '))
  assert.equal(parts.join(' '), paragraph)
})

test('a sentence longer than an utterance is cut at a pause', () => {
  const clause = 'and then the long sentence went on without ever stopping'
  const sentence = `${Array.from({ length: 6 }, () => clause).join(', ')}.`
  const parts = utterances(sentence)
  assert.ok(parts.length > 1)
  for (const part of parts) assert.ok(part.length <= LONGEST_UTTERANCE, part)
  assert.ok(parts[0].endsWith(','))
  assert.equal(parts.join(' '), sentence)
})

test('a run of text with no spaces is still cut to size', () => {
  const parts = utterances('x'.repeat(LONGEST_UTTERANCE * 2 + 5))
  assert.deepEqual(
    parts.map((part) => part.length),
    [LONGEST_UTTERANCE, LONGEST_UTTERANCE, 5],
  )
})

test('reading starts from the paragraph under the reading line', () => {
  assert.equal(firstUnread([100, 200, 300], 150), 1)
  assert.equal(firstUnread([100, 200, 300], 50), 0)
  assert.equal(firstUnread([100, 200, 300], 400), 0)
})

test('plays every utterance of every paragraph in order, then stops', () => {
  const { fake, shown, states } = player([['a1', 'a2'], ['b1']])
  fake.finish()
  fake.finish()
  fake.finish()
  assert.deepEqual(
    fake.spoken.map((item) => item.text),
    ['a1', 'a2', 'b1'],
  )
  assert.deepEqual(shown, [0, 1, null])
  assert.deepEqual(states, ['playing', 'stopped'])
})

test('starts from the paragraph it is given', () => {
  const { fake, shown } = player([['a'], ['b'], ['c']], 1)
  assert.deepEqual(fake.spoken.map((item) => item.text), ['b'])
  assert.deepEqual(shown, [1])
})

test('a pause restarts the same utterance on resume', async () => {
  const { fake, reader, states } = player([['a1', 'a2']])
  fake.finish()
  reader.pause()
  await settle()
  reader.resume()
  assert.deepEqual(
    fake.spoken.map((item) => item.text),
    ['a1', 'a2', 'a2'],
  )
  assert.deepEqual(states, ['playing', 'paused', 'playing'])
})

test('a cancelled utterance reporting late never moves the reader on', async () => {
  const { fake, reader, shown } = player([['a'], ['b'], ['c']])
  reader.skip(1)
  await settle()
  assert.equal(reader.state, 'playing')
  assert.deepEqual(shown, [0, 1])
  assert.deepEqual(fake.spoken.map((item) => item.text), ['a', 'b'])
})

test('skipping moves a whole paragraph and clamps at the start', () => {
  const { fake, reader, shown } = player([['a1', 'a2'], ['b']])
  fake.finish()
  reader.skip(-1)
  reader.skip(-1)
  assert.deepEqual(shown, [0, 0, 0])
  assert.deepEqual(fake.spoken.map((item) => item.text), ['a1', 'a2', 'a1', 'a1'])
})

test('skipping past the last paragraph stops', () => {
  const { reader, shown, states } = player([['a']])
  reader.skip(1)
  assert.deepEqual(shown, [0, null])
  assert.deepEqual(states, ['playing', 'stopped'])
})

test('skipping while paused moves without speaking', () => {
  const { fake, reader, shown } = player([['a'], ['b']])
  reader.pause()
  reader.skip(1)
  assert.equal(reader.state, 'paused')
  assert.deepEqual(shown, [0, 1])
  assert.equal(fake.spoken.length, 1)
})

test('a new rate is heard from the current utterance', () => {
  const { fake, reader } = player([['a']])
  reader.configure({ voice: 'v', rate: 1.5 })
  assert.deepEqual(fake.spoken.at(-1), { text: 'a', settings: { voice: 'v', rate: 1.5 } })
})

test('an utterance the engine fails stops reading', () => {
  const fake = fakeEngine()
  const states: PlayState[] = []
  const engine: SpeechEngine = { ...fake.engine, speak: (_text, _settings, done) => done(false) }
  const reader = new ReadAloudPlayer(
    engine,
    { block: () => {}, state: (state) => states.push(state) },
    { voice: null, rate: 1 },
  )
  reader.start([['a'], ['b']], 0)
  assert.deepEqual(states, ['playing', 'stopped'])
})

test('stop silences the engine and clears the highlight', () => {
  const { fake, reader, shown } = player([['a']])
  reader.stop()
  assert.ok(fake.cancels > 0)
  assert.deepEqual(shown, [0, null])
  assert.equal(reader.state, 'stopped')
})

test('nothing to read stops straight away', () => {
  const { fake, reader, states } = player([])
  assert.equal(reader.state, 'stopped')
  assert.deepEqual(states, [])
  assert.equal(fake.spoken.length, 0)
})

/** A player whose events are kept in the order they arrived, `finished` among them. */
function watched(blocks: string[][], onFinished: () => void = () => {}) {
  const fake = fakeEngine()
  const order: string[] = []
  const reader = new ReadAloudPlayer(
    fake.engine,
    {
      block: () => {},
      state: (state) => order.push(state),
      finished: () => {
        order.push('finished')
        onFinished()
      },
    },
    { voice: null, rate: 1 },
  )
  reader.start(blocks, 0)
  return { fake, reader, order }
}

test('running out of text is reported once, after stopping', () => {
  const { fake, order } = watched([['a'], ['b']])
  fake.finish()
  assert.deepEqual(order, ['playing'])
  fake.finish()
  assert.deepEqual(order, ['playing', 'stopped', 'finished'])
})

test('stopping by hand is not running out', async () => {
  const { reader, order } = watched([['a'], ['b']])
  reader.stop()
  await settle()
  assert.deepEqual(order, ['playing', 'stopped'])
})

test('an utterance the engine gave up on is not running out', () => {
  const fake = fakeEngine()
  const order: string[] = []
  const engine: SpeechEngine = { ...fake.engine, speak: (_text, _settings, done) => done(false) }
  const reader = new ReadAloudPlayer(
    engine,
    { block: () => {}, state: (state) => order.push(state), finished: () => order.push('finished') },
    { voice: null, rate: 1 },
  )
  reader.start([['a']], 0)
  assert.deepEqual(order, ['playing', 'stopped'])
})

test('skipping past the end is not running out', async () => {
  const { reader, order } = watched([['a'], ['b']])
  reader.skip(5)
  await settle()
  assert.deepEqual(order, ['playing', 'stopped'])
})

test('a player started again from finished speaks the new text', () => {
  let again = true
  const run = watched([['a']], () => {
    if (!again) return
    again = false
    run.reader.start([['next page']], 0)
  })
  run.fake.finish()
  assert.equal(run.fake.spoken.at(-1)?.text, 'next page')
  assert.equal(run.reader.state, 'playing')
  run.fake.finish()
  assert.deepEqual(run.order, ['playing', 'stopped', 'finished', 'playing', 'stopped', 'finished'])
})

const wait = (ms: number) => new Promise((done) => setTimeout(done, ms))

/** A player started with a silence to keep after each block. */
function rested(blocks: string[][], rests: number[]) {
  const fake = fakeEngine()
  const shown: (number | null)[] = []
  const reader = new ReadAloudPlayer(
    fake.engine,
    { block: (index) => shown.push(index), state: () => {} },
    { voice: null, rate: 1 },
  )
  reader.start(blocks, 0, rests)
  return { fake, reader, shown }
}

test('a rest after a block holds the next one back', async () => {
  const { fake } = rested([['a'], ['b']], [40])
  fake.finish()
  await wait(10)
  assert.equal(fake.spoken.length, 1)
  await wait(60)
  assert.equal(fake.spoken.at(-1)?.text, 'b')
})

test('a rest is kept between blocks, not between the pieces of one', () => {
  const { fake } = rested([['a', 'still a'], ['b']], [40])
  fake.finish()
  assert.equal(fake.spoken.at(-1)?.text, 'still a')
})

test('pausing during a rest keeps the next block unsaid until resumed', async () => {
  const { fake, reader } = rested([['a'], ['b']], [40])
  fake.finish()
  reader.pause()
  await wait(80)
  assert.equal(fake.spoken.length, 1)
  reader.resume()
  assert.equal(fake.spoken.at(-1)?.text, 'b')
})

test('stopping during a rest says nothing more', async () => {
  const { fake, reader } = rested([['a'], ['b']], [40])
  fake.finish()
  reader.stop()
  await wait(80)
  assert.equal(fake.spoken.length, 1)
  assert.equal(reader.state, 'stopped')
})

test('stepping on during a rest speaks the block stepped to at once', async () => {
  const { fake, reader } = rested([['a'], ['b'], ['c']], [40, 40])
  fake.finish()
  reader.skip(1)
  assert.equal(fake.spoken.at(-1)?.text, 'c')
  await wait(80)
  assert.equal(fake.spoken.filter((said) => said.text === 'b').length, 0)
})

test('there is no rest after the last block: running out is reported at once', () => {
  const fake = fakeEngine()
  let finished = 0
  const reader = new ReadAloudPlayer(
    fake.engine,
    { block: () => {}, state: () => {}, finished: () => (finished += 1) },
    { voice: null, rate: 1 },
  )
  reader.start([['a']], 0, [40])
  fake.finish()
  assert.equal(finished, 1)
})
