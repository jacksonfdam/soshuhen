// Read-aloud without a DOM or a voice: what to say, in what pieces, and in what
// order. Kept free of imports and of TypeScript-only syntax so `node --test`
// can run it as it is, with a fake engine standing in for the browser.

/**
 * Chrome stops an utterance after roughly fifteen seconds of speech and never
 * says so: the rest of the paragraph is silently lost. A couple of hundred
 * characters is well inside that at any rate the reader offers.
 */
export const LONGEST_UTTERANCE = 220

export interface SpeechVoice {
  id: string
  name: string
  lang: string
}

export interface SpeechSettings {
  voice: string | null
  rate: number
}

/**
 * What the player needs from a voice. Small on purpose: the browser's
 * `speechSynthesis` is one engine, and a server that renders audio can be
 * another without the player changing. `done` is called once per `speak`,
 * with false when the utterance did not finish (cancelled or failed).
 */
export interface SpeechEngine {
  voices(): SpeechVoice[]
  onVoicesChanged(listener: () => void): () => void
  speak(text: string, settings: SpeechSettings, done: (finished: boolean) => void): void
  cancel(): void
}

function sentences(text: string): string[] {
  if (typeof Intl.Segmenter === 'function') {
    return [...new Intl.Segmenter(undefined, { granularity: 'sentence' }).segment(text)].map(
      (part) => part.segment,
    )
  }
  return text.match(/[^.!?…]+(?:[.!?…]+["'”’)\]]*\s*|$)/g) ?? [text]
}

/** A sentence too long to say at once, cut at a pause if it has one. */
function cut(sentence: string): string[] {
  const pieces: string[] = []
  let rest = sentence
  while (rest.length > LONGEST_UTTERANCE) {
    const window = rest.slice(0, LONGEST_UTTERANCE)
    const pause = Math.max(
      window.lastIndexOf(', '),
      window.lastIndexOf('; '),
      window.lastIndexOf(': '),
      window.lastIndexOf('— '),
    )
    const space = window.lastIndexOf(' ')
    const at = pause > LONGEST_UTTERANCE / 2 ? pause + 1 : space > 0 ? space : LONGEST_UTTERANCE
    pieces.push(rest.slice(0, at).trim())
    rest = rest.slice(at).trim()
  }
  if (rest) pieces.push(rest)
  return pieces
}

/**
 * A paragraph as the utterances it is spoken in: whole when it is short, and
 * otherwise by sentence, with short sentences put back together so a run of
 * dialogue is not read with a pause after every line.
 */
export function utterances(paragraph: string): string[] {
  const text = paragraph.replace(/\s+/g, ' ').trim()
  if (!text) return []
  if (text.length <= LONGEST_UTTERANCE) return [text]
  const merged: string[] = []
  for (const piece of sentences(text).map((part) => part.trim()).filter(Boolean).flatMap(cut)) {
    const last = merged.length - 1
    if (last >= 0 && merged[last].length + 1 + piece.length <= LONGEST_UTTERANCE) {
      merged[last] = `${merged[last]} ${piece}`
    } else {
      merged.push(piece)
    }
  }
  return merged
}

/**
 * The paragraph reading should start from: the first whose bottom edge is
 * below the reading line, which is the one the eye is on. Past the last one,
 * the book is read again from the start.
 */
export function firstUnread(bottoms: number[], line: number): number {
  const index = bottoms.findIndex((bottom) => bottom > line)
  return index === -1 ? 0 : index
}

export type PlayState = 'stopped' | 'playing' | 'paused'

export interface PlayerEvents {
  /** The paragraph now being read, or null once nothing is. */
  block(index: number | null): void
  state(state: PlayState): void
}

/**
 * Speaks a list of paragraphs one utterance at a time.
 *
 * Pausing cancels rather than calling the engine's own pause: Chrome on
 * Android never resumes a paused utterance, and an engine that renders audio
 * has nothing to pause mid-request. Resuming restarts the utterance, which is
 * at most a sentence. Every `speak` carries a turn number, so the late `done`
 * of an utterance that was cancelled can never move the reader on.
 */
export class ReadAloudPlayer {
  private engine: SpeechEngine
  private events: PlayerEvents
  private settings: SpeechSettings
  private blocks: string[][] = []
  private block = 0
  private piece = 0
  private turn = 0
  private current: PlayState = 'stopped'

  constructor(engine: SpeechEngine, events: PlayerEvents, settings: SpeechSettings) {
    this.engine = engine
    this.events = events
    this.settings = settings
  }

  get state(): PlayState {
    return this.current
  }

  start(blocks: string[][], from: number) {
    this.silence()
    this.blocks = blocks
    if (from >= blocks.length) {
      this.stop()
      return
    }
    this.block = Math.max(0, from)
    this.piece = 0
    this.events.block(this.block)
    this.become('playing')
    this.speak()
  }

  pause() {
    if (this.current !== 'playing') return
    this.silence()
    this.become('paused')
  }

  resume() {
    if (this.current !== 'paused') return
    this.become('playing')
    this.speak()
  }

  /** Moves a paragraph back or forward; a pause stays paused there. */
  skip(delta: number) {
    if (this.current === 'stopped') return
    const target = Math.max(0, this.block + delta)
    if (target >= this.blocks.length) {
      this.stop()
      return
    }
    this.silence()
    this.block = target
    this.piece = 0
    this.events.block(this.block)
    if (this.current === 'playing') this.speak()
  }

  /** A new voice or rate is heard from the current utterance, not the next paragraph. */
  configure(settings: SpeechSettings) {
    this.settings = settings
    if (this.current !== 'playing') return
    this.silence()
    this.speak()
  }

  stop() {
    this.silence()
    if (this.current === 'stopped') return
    this.events.block(null)
    this.become('stopped')
  }

  private silence() {
    this.turn += 1
    this.engine.cancel()
  }

  private become(state: PlayState) {
    this.current = state
    this.events.state(state)
  }

  private speak() {
    const turn = ++this.turn
    this.engine.speak(this.blocks[this.block][this.piece], this.settings, (finished) => {
      if (turn !== this.turn) return
      // An utterance the engine gave up on is not one to skip past silently.
      if (!finished) {
        this.stop()
        return
      }
      this.advance()
    })
  }

  private advance() {
    this.piece += 1
    if (this.piece >= this.blocks[this.block].length) {
      this.piece = 0
      this.block += 1
      if (this.block >= this.blocks.length) {
        this.stop()
        return
      }
      this.events.block(this.block)
    }
    this.speak()
  }
}
