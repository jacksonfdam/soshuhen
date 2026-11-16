import { useCallback, useEffect, useRef, useState } from 'react'

import {
  ReadAloudPlayer,
  firstUnread,
  utterances,
  type PlayState,
  type SpeechSettings,
  type SpeechVoice,
} from './readAloud'
import { anchor, scrollToPlace } from './useProsePosition'
import { webSpeechEngine } from './webSpeech'

const KEY = 'reader:read-aloud'
const DEFAULT: SpeechSettings = { voice: null, rate: 1 }

// The book's own tags that hold a paragraph's worth of words. A `div` counts
// only when nothing in it does: some EPUBs write every paragraph as one.
const BLOCKS = 'p, li, blockquote, h1, h2, h3, h4, h5, h6, figcaption, th, td, div'
// Styled from the stylesheet: the book's markup cannot carry classes.
const SPEAKING = 'data-speaking'

/** Per device rather than per account: voices differ between browsers. */
function savedSettings(): SpeechSettings {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? 'null')
    if (typeof value !== 'object' || value === null) return DEFAULT
    const { voice, rate } = value as Record<string, unknown>
    return {
      voice: typeof voice === 'string' ? voice : null,
      rate: typeof rate === 'number' && rate > 0 ? rate : DEFAULT.rate,
    }
  } catch {
    return DEFAULT
  }
}

function saveSettings(settings: SpeechSettings) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    // A private window refuses storage; the choice lasts until the tab closes.
  }
}

function readableBlocks(column: HTMLElement) {
  return [...column.querySelectorAll<HTMLElement>(BLOCKS)]
    .filter((element) => !element.querySelector(BLOCKS))
    // innerText, not textContent: a `br` between two lines is a space to a
    // listener, and textContent runs the words together.
    .map((element) => ({ element, parts: utterances(element.innerText) }))
    .filter((block) => block.parts.length > 0)
}

/** Brings a paragraph to the reading line through the reader's own scroll,
    which is also what saves the place as it moves. */
function follow(column: HTMLElement, element: HTMLElement) {
  const section = element.closest<HTMLElement>('[data-section]')
  if (!section) return
  const box = section.getBoundingClientRect()
  const top = element.getBoundingClientRect().top - box.top
  scrollToPlace(column, Number(section.dataset.section), box.height > 0 ? top / box.height : 0)
}

/**
 * Reads the book aloud from where the reader is, a paragraph at a time.
 *
 * `supported` is false where the browser cannot speak, and nothing else here
 * does anything then. Reading stops when the screen goes away.
 */
export function useReadAloud(column: HTMLElement | null) {
  const [engine] = useState(webSpeechEngine)
  const [state, setState] = useState<PlayState>('stopped')
  const [voices, setVoices] = useState<SpeechVoice[]>([])
  const [settings, setSettings] = useState(savedSettings)
  const elements = useRef<HTMLElement[]>([])
  const lit = useRef<HTMLElement | null>(null)
  const columnRef = useRef(column)
  columnRef.current = column

  const [player] = useState(
    () =>
      engine &&
      new ReadAloudPlayer(
        engine,
        {
          block(index) {
            lit.current?.removeAttribute(SPEAKING)
            const element = index === null ? null : (elements.current[index] ?? null)
            lit.current = element
            if (!element) return
            element.setAttribute(SPEAKING, '')
            if (columnRef.current) follow(columnRef.current, element)
          },
          state: setState,
        },
        settings,
      ),
  )

  // Voices arrive after the page does, in Chrome only once asked for.
  useEffect(() => {
    if (!engine) return
    setVoices(engine.voices())
    return engine.onVoicesChanged(() => setVoices(engine.voices()))
  }, [engine])

  useEffect(() => () => player?.stop(), [player])

  const toggle = useCallback(() => {
    if (!player) return
    if (player.state === 'playing') player.pause()
    else if (player.state === 'paused') player.resume()
    else if (column) {
      const blocks = readableBlocks(column)
      elements.current = blocks.map((block) => block.element)
      const bottoms = blocks.map((block) => block.element.getBoundingClientRect().bottom)
      player.start(
        blocks.map((block) => block.parts),
        firstUnread(bottoms, anchor()),
      )
    }
  }, [player, column])

  const skip = useCallback((delta: number) => player?.skip(delta), [player])
  const stop = useCallback(() => player?.stop(), [player])

  const configure = useCallback(
    (next: SpeechSettings) => {
      setSettings(next)
      saveSettings(next)
      player?.configure(next)
    },
    [player],
  )

  return { supported: player !== null, state, voices, settings, toggle, skip, stop, configure }
}
