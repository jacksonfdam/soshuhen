// Narration of a chapter, without React or a DOM: which page is read, when it
// is turned, and what happens when a page cannot be read. Kept that way so
// `node --test` can run it with a fake voice; the imports carry their `.ts`
// for the same reason.

import type { PageTranscript } from '../../../lib/api'
import {
  ReadAloudPlayer,
  utterances,
  type PlayState,
  type SpeechEngine,
  type SpeechSettings,
} from '../../../lib/readAloud.ts'
import {
  CHAPTER_END,
  failureScript,
  pageScript,
  restsFor,
  type ScriptItem,
} from './narrationScript.ts'

/** What narration needs from the reader it is narrating. */
export interface NarrationHost {
  pageCount(): number
  transcript(page: number): Promise<PageTranscript>
  /**
   * Everything on screen has been read: turn the page. Answers `end` when
   * there was no page to turn to and the chapter is over.
   */
  pagesDone(): 'continue' | 'end'
  /** Something a screen would draw has changed. */
  changed(): void
}

/**
 * Reads the pages on screen aloud and asks for the next ones.
 *
 * Being on is separate from speaking: narration stays on across a page turn,
 * a pause, and a page it could not read, and goes off only when asked to or
 * when the chapter ends.
 */
export class Narration {
  /** Every page read so far in this chapter, for the transcript panel. */
  readonly transcripts = new Map<number, PageTranscript>()

  private host: NarrationHost
  private player: ReadAloudPlayer
  private asking = new Map<number, Promise<PageTranscript>>()
  private pages: number[] = []
  private items: ScriptItem[] = []
  private speaking: number | null = null
  private isOn = false
  private ending = false
  private failedPage: number | null = null
  // Counts every change of what should be read. An answer from the narrator
  // carries the number it was asked under, and is spoken only if that is
  // still the number: pages turned quickly would otherwise be read out one
  // after another, long after they left the screen.
  private turn = 0
  // Counts changes of reading direction. A transcript is an order as much as
  // it is text, so one asked for under the old direction is not kept.
  private era = 0
  private settleMs: number
  private paced: boolean
  private settling: ReturnType<typeof setTimeout> | null = null

  /**
   * `settleMs` is how long a page must stay on screen before the narrator is
   * asked about it. A listener holding an arrow key passes a page every few
   * dozen milliseconds, and each one asked for is a second of the narrator's
   * time spent on a page nobody will hear, ahead of the one they stop on.
   *
   * `paced` keeps the script's silences between lines and panels. The reader
   * always asks for them; the tests mostly do not, so they need not wait.
   */
  constructor(
    engine: SpeechEngine,
    settings: SpeechSettings,
    host: NarrationHost,
    settleMs = 0,
    paced = false,
  ) {
    this.host = host
    this.settleMs = settleMs
    this.paced = paced
    this.player = new ReadAloudPlayer(
      engine,
      {
        block: (index) => {
          this.speaking = index
          this.changed()
        },
        state: () => this.changed(),
        finished: () => this.scriptDone(),
      },
      settings,
    )
  }

  get on(): boolean {
    return this.isOn
  }

  get state(): PlayState {
    return this.player.state
  }

  /** What is being spoken, or null between pages and while the end is said. */
  get place(): ScriptItem | null {
    return this.speaking === null ? null : (this.items[this.speaking] ?? null)
  }

  /** The page that could not be read, while narration is waiting on it. */
  get failed(): number | null {
    return this.failedPage
  }

  /** The pages now on screen, in page order. None means the end screen. */
  show(pages: number[]) {
    if (pages.length === this.pages.length && pages.every((page, at) => page === this.pages[at])) {
      return
    }
    this.pages = pages
    if (!this.isOn) return
    if (pages.length > 0) this.readSoon()
    // The end screen also appears because narration itself turned the last
    // page; saying the end a second time over the first would cut it off.
    else if (!this.ending) this.end()
  }

  toggle() {
    if (this.isOn) {
      this.turnOff()
      return
    }
    this.isOn = true
    this.changed()
    if (this.pages.length > 0) this.read()
    else this.end()
  }

  /** The player's own button: pause and resume, or try a failed page again. */
  playPause() {
    if (!this.isOn) return
    if (this.player.state === 'playing') this.player.pause()
    else if (this.player.state === 'paused') this.player.resume()
    else if (this.pages.length > 0 && !this.ending) this.read()
  }

  skip(delta: number) {
    if (!this.isOn || this.ending || this.player.state === 'stopped') return
    // Past the last line is the next page, not silence: the player alone
    // would stop there and leave a listener wondering why.
    if ((this.speaking ?? 0) + delta >= this.items.length) {
      this.player.stop()
      this.scriptDone()
      return
    }
    this.player.skip(delta)
  }

  configure(settings: SpeechSettings) {
    this.player.configure(settings)
  }

  /** The reading direction changed: what was read was read in the old order. */
  forget() {
    this.era += 1
    this.transcripts.clear()
    this.asking.clear()
    this.changed()
    if (this.isOn && this.pages.length > 0 && !this.ending) this.read()
  }

  /**
   * The reader is going away: nothing asked for so far is spoken. Not final,
   * because React's strict mode unmounts and remounts a screen once in
   * development, and the narration it remounts with is this same one.
   */
  dispose() {
    this.isOn = false
    this.turn += 1
    this.unsettle()
    this.player.stop()
  }

  private turnOff() {
    this.isOn = false
    this.turn += 1
    this.unsettle()
    this.ending = false
    this.failedPage = null
    this.items = []
    this.player.stop()
    this.changed()
  }

  /** Read the pages on screen once they have stayed there a moment. */
  private readSoon() {
    if (this.settleMs <= 0) {
      this.read()
      return
    }
    // Silent at once, though: what was being said is about a page that has
    // left the screen, whether or not the next one stays.
    this.turn += 1
    this.unsettle()
    this.ending = false
    this.failedPage = null
    this.items = []
    this.player.stop()
    this.changed()
    this.settling = setTimeout(() => {
      this.settling = null
      this.read()
    }, this.settleMs)
  }

  private unsettle() {
    if (this.settling !== null) clearTimeout(this.settling)
    this.settling = null
  }

  private read() {
    this.unsettle()
    const mine = ++this.turn
    const pages = this.pages
    this.ending = false
    this.failedPage = null
    this.items = []
    this.player.stop()
    this.changed()

    const answers = pages.map((page) =>
      this.ask(page).then(
        (transcript) => ({ page, transcript }),
        () => ({ page, transcript: null }),
      ),
    )
    void Promise.all(answers).then((found) => {
      if (mine !== this.turn || !this.isOn) return
      for (const { page, transcript } of found) {
        if (transcript !== null) {
          this.items.push(...pageScript(page, transcript))
          continue
        }
        this.items.push(...failureScript(page))
        this.failedPage ??= page
      }
      this.player.start(
        this.items.map((item) => utterances(item.text)),
        0,
        this.paced ? restsFor(this.items) : [],
      )
      this.changed()

      // Asked for now so it is there when the page turns. A failure here is
      // nobody's business yet: the page is asked for again when it is shown.
      const ahead = pages[pages.length - 1] + 1
      if (ahead < this.host.pageCount()) void this.ask(ahead).catch(() => undefined)
    })
  }

  /** A page's transcript, asked of the narrator once however often it is wanted. */
  private ask(page: number): Promise<PageTranscript> {
    const known = this.transcripts.get(page)
    if (known) return Promise.resolve(known)
    const underway = this.asking.get(page)
    if (underway) return underway
    const era = this.era
    const asked = this.host.transcript(page).then(
      (transcript) => {
        // An answer from before the direction changed is handed to whoever
        // asked and kept by nobody; the entry under this page's name by then
        // belongs to a newer request.
        if (era !== this.era) return transcript
        this.asking.delete(page)
        this.transcripts.set(page, transcript)
        this.changed()
        return transcript
      },
      (failure: unknown) => {
        // Forgotten rather than remembered as a failure, so the next time the
        // page is wanted the narrator is asked again.
        if (era === this.era) this.asking.delete(page)
        throw failure
      },
    )
    this.asking.set(page, asked)
    return asked
  }

  private scriptDone() {
    if (!this.isOn) return
    if (this.ending) {
      this.turnOff()
      return
    }
    // A page that could not be read is waited on, not walked past: turning it
    // would say the same sentence for every page left in the chapter and mark
    // the chapter finished at the end of it.
    if (this.failedPage !== null) return
    if (this.host.pagesDone() === 'end') this.end()
  }

  private end() {
    this.turn += 1
    this.unsettle()
    this.ending = true
    this.failedPage = null
    this.items = []
    this.player.start([utterances(CHAPTER_END)], 0)
    this.changed()
  }

  private changed() {
    this.host.changed()
  }
}
