import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { SpeechEngine } from '../../../lib/readAloud.ts'
import { Narration } from './narration.ts'
import { CHAPTER_END, UNREADABLE } from './narrationScript.ts'

/** A transcript with one panel per argument, each holding the given lines. */
const transcript = (...panels: string[][]) => ({
  engine: 'fake',
  language: 'en',
  width: 1,
  height: 1,
  panels: panels.map((lines) => ({
    box: [0, 0, 1, 1],
    blocks: lines.map((text) => ({ box: [0, 0, 1, 1], text })),
  })),
})

/** Stands in for `speechSynthesis`: an utterance ends only when the test says. */
function fakeEngine() {
  const spoken: string[] = []
  const pending: ((finished: boolean) => void)[] = []
  const engine: SpeechEngine = {
    voices: () => [],
    onVoicesChanged: () => () => {},
    speak(text, _settings, done) {
      spoken.push(text)
      pending.push(done)
    },
    cancel() {
      // The browser reports a cancelled utterance as an error, late.
      for (const done of pending.splice(0)) queueMicrotask(() => done(false))
    },
  }
  return {
    engine,
    spoken,
    /** Let the utterance being spoken end, and whatever follows from it settle. */
    async finish() {
      const done = pending.shift()
      assert.ok(done, 'nothing is being spoken')
      done(true)
      await settle()
    },
    /** Speak to the end of everything queued for the page. */
    async finishAll() {
      while (pending.length > 0) await this.finish()
    },
  }
}

const settle = () => new Promise((done) => setTimeout(done, 0))

type Answer = ReturnType<typeof transcript> | Error

/**
 * A reader with `pages` pages. Each page's transcript is an entry of `book`:
 * a transcript, an Error for a page the narrator cannot read, or absent for a
 * page whose answer the test delivers itself through `deliver`.
 */
function reader(pages: number, book: Record<number, Answer> = {}) {
  const fake = fakeEngine()
  const asked: number[] = []
  const waiting = new Map<number, (answer: Answer) => void>()
  let turned = 0
  let changes = 0
  let next: 'continue' | 'end' = 'continue'
  const narration = new Narration(
    fake.engine,
    { voice: null, rate: 1 },
    {
      pageCount: () => pages,
      transcript(page) {
        asked.push(page)
        return new Promise((resolve, reject) => {
          const settleWith = (answer: Answer) =>
            answer instanceof Error ? reject(answer) : resolve(answer)
          if (page in book) settleWith(book[page])
          else waiting.set(page, settleWith)
        })
      },
      pagesDone() {
        turned += 1
        return next
      },
      changed() {
        changes += 1
      },
    },
  )
  return {
    fake,
    narration,
    asked,
    get turned() {
      return turned
    },
    get changes() {
      return changes
    },
    endsNext() {
      next = 'end'
    },
    async deliver(page: number, answer: Answer) {
      const settleWith = waiting.get(page)
      assert.ok(settleWith, `page ${page} was not asked for`)
      waiting.delete(page)
      settleWith(answer)
      await settle()
    },
  }
}

test('turning it on reads the page on screen', async () => {
  const run = reader(3, { 0: transcript(['Good morning.', 'Where are you going?']) })
  run.narration.show([0])
  assert.deepEqual(run.fake.spoken, [])

  run.narration.toggle()
  await settle()
  await run.fake.finishAll()

  assert.deepEqual(run.fake.spoken, ['Page 1.', 'Good morning.', 'Where are you going?'])
  assert.equal(run.narration.on, true)
})

test('the page is turned once when its text runs out, and the next one is read when shown', async () => {
  const run = reader(3, { 0: transcript(['One.']), 1: transcript(['Two.']) })
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  await run.fake.finishAll()
  assert.equal(run.turned, 1)

  run.narration.show([1])
  await settle()
  await run.fake.finishAll()

  assert.deepEqual(run.fake.spoken, ['Page 1.', 'One.', 'Page 2.', 'Two.'])
  assert.equal(run.turned, 2)
})

test('both pages of a spread are read, in page order, before it is turned', async () => {
  const run = reader(5, { 1: transcript(['Left.']), 2: transcript(['Right.']) })
  run.narration.show([1, 2])
  run.narration.toggle()
  await settle()
  await run.fake.finishAll()

  assert.deepEqual(run.fake.spoken, ['Page 2.', 'Left.', 'Page 3.', 'Right.'])
  assert.equal(run.turned, 1)
})

test('a page that cannot be read says so once and is not turned', async () => {
  const run = reader(3, { 0: new Error('502') })
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  await run.fake.finishAll()

  assert.deepEqual(run.fake.spoken, ['Page 1.', UNREADABLE])
  assert.equal(run.turned, 0)
  assert.equal(run.narration.failed, 0)
  assert.equal(run.narration.on, true)
})

test('a spread with one unreadable page reads the other and still is not turned', async () => {
  const run = reader(5, { 1: transcript(['Left.']), 2: new Error('502') })
  run.narration.show([1, 2])
  run.narration.toggle()
  await settle()
  await run.fake.finishAll()

  assert.deepEqual(run.fake.spoken, ['Page 2.', 'Left.', 'Page 3.', UNREADABLE])
  assert.equal(run.turned, 0)
  assert.equal(run.narration.failed, 2)
})

test('pressing play on a page that failed asks the narrator again', async () => {
  const run = reader(3, { 0: new Error('502') })
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  await run.fake.finishAll()

  run.narration.playPause()
  await settle()

  assert.equal(run.asked.filter((page) => page === 0).length, 2)
})

test('a transcript that arrives for a page no longer on screen is not spoken', async () => {
  const run = reader(5, { 3: transcript(['The page that stayed.']) })
  run.narration.show([0])
  run.narration.toggle()
  run.narration.show([1])
  run.narration.show([2])
  run.narration.show([3])
  await settle()

  await run.deliver(0, transcript(['Left behind.']))
  await run.deliver(1, transcript(['Also left behind.']))
  await run.fake.finishAll()

  assert.deepEqual(run.fake.spoken, ['Page 4.', 'The page that stayed.'])
  assert.equal(run.turned, 1)
})

test('a transcript that arrives after narration was turned off is not spoken', async () => {
  const run = reader(3)
  run.narration.show([0])
  run.narration.toggle()
  run.narration.toggle()

  await run.deliver(0, transcript(['Too late.']))

  assert.deepEqual(run.fake.spoken, [])
  assert.equal(run.narration.on, false)
})

test('the end of the chapter is said once, and narration turns itself off', async () => {
  const run = reader(1, { 0: transcript(['The last line.']) })
  run.endsNext()
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  await run.fake.finishAll()

  assert.deepEqual(run.fake.spoken, ['Page 1.', 'The last line.', CHAPTER_END])
  assert.equal(run.narration.on, false)
  assert.equal(run.turned, 1)
})

test('the end screen appearing while the end is being said does not cut it off', async () => {
  const run = reader(1, { 0: transcript(['The last line.']) })
  run.endsNext()
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  await run.fake.finish()
  await run.fake.finish()
  assert.equal(run.fake.spoken.at(-1), CHAPTER_END)

  run.narration.show([])
  await run.fake.finishAll()

  assert.equal(run.fake.spoken.filter((text) => text === CHAPTER_END).length, 1)
  assert.equal(run.narration.on, false)
})

test('reaching the end screen by hand says the end and turns narration off', async () => {
  const run = reader(2, { 1: transcript(['Nearly there.']) })
  run.narration.show([1])
  run.narration.toggle()
  await settle()

  run.narration.show([])
  await settle()
  await run.fake.finishAll()

  assert.equal(run.fake.spoken.at(-1), CHAPTER_END)
  assert.equal(run.narration.on, false)
  assert.equal(run.turned, 0)
})

test('each page is asked of the narrator once', async () => {
  const run = reader(3, { 0: transcript(['One.']), 1: transcript(['Two.']) })
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  run.narration.show([1])
  await settle()
  run.narration.show([0])
  await settle()

  assert.equal(run.asked.filter((page) => page === 0).length, 1)
  assert.equal(run.asked.filter((page) => page === 1).length, 1)
})

test('the page after the one on screen is asked for ahead of time', async () => {
  const run = reader(3, { 0: transcript(['One.']), 1: transcript(['Two.']) })
  run.narration.show([0])
  run.narration.toggle()
  await settle()

  assert.deepEqual(run.asked, [0, 1])
  assert.deepEqual(run.fake.spoken, ['Page 1.'])
})

test('nothing past the last page is asked for', async () => {
  const run = reader(2, { 1: transcript(['The last.']) })
  run.narration.show([1])
  run.narration.toggle()
  await settle()

  assert.deepEqual(run.asked, [1])
})

test('a page asked for ahead that fails is asked again when it is shown', async () => {
  const run = reader(3, { 0: transcript(['One.']), 1: new Error('502') })
  run.narration.show([0])
  run.narration.toggle()
  await settle()

  run.narration.show([1])
  await settle()

  assert.equal(run.asked.filter((page) => page === 1).length, 2)
})

test('stepping forward past the last line turns the page', async () => {
  const run = reader(3, { 0: transcript(['Only line.']) })
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  await run.fake.finish()
  assert.equal(run.fake.spoken.at(-1), 'Only line.')

  run.narration.skip(1)
  await settle()

  assert.equal(run.turned, 1)
})

test('stepping back from the first thing said stays on the page', async () => {
  const run = reader(3, { 0: transcript(['Only line.']) })
  run.narration.show([0])
  run.narration.toggle()
  await settle()

  run.narration.skip(-1)
  await settle()

  assert.equal(run.turned, 0)
  assert.equal(run.fake.spoken.at(-1), 'Page 1.')
})

test('what is being spoken is reported, and cleared when narration is turned off', async () => {
  const run = reader(3, { 0: transcript(['First.'], ['Second.']) })
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  assert.deepEqual(run.narration.place, { text: 'Page 1.', page: 0, panel: null, block: null })

  await run.fake.finish()
  await run.fake.finish()
  assert.deepEqual(run.narration.place, { text: 'First.', page: 0, panel: 0, block: 0 })

  run.narration.toggle()
  assert.equal(run.narration.place, null)
})

test('pausing keeps narration on, and resuming goes on with the same line', async () => {
  const run = reader(3, { 0: transcript(['A line.']) })
  run.narration.show([0])
  run.narration.toggle()
  await settle()
  await run.fake.finish()

  run.narration.playPause()
  await settle()
  assert.equal(run.narration.state, 'paused')
  assert.equal(run.narration.on, true)

  run.narration.playPause()
  await settle()
  assert.equal(run.narration.state, 'playing')
  assert.equal(run.fake.spoken.at(-1), 'A line.')
  assert.equal(run.turned, 0)
})

test('transcripts read so far are kept for the transcript panel', async () => {
  const first = transcript(['One.'])
  const run = reader(3, { 0: first })
  run.narration.show([0])
  run.narration.toggle()
  await settle()

  assert.equal(run.narration.transcripts.get(0), first)
})

test('the screen is told when something it shows has changed', async () => {
  const run = reader(3, { 0: transcript(['One.']) })
  run.narration.show([0])
  const before = run.changes

  run.narration.toggle()
  await settle()

  assert.ok(run.changes > before)
})

test('disposing silences it for good', async () => {
  const run = reader(3)
  run.narration.show([0])
  run.narration.toggle()
  run.narration.dispose()

  await run.deliver(0, transcript(['After the reader was left.']))

  assert.deepEqual(run.fake.spoken, [])
})
