import { useCallback, useEffect, useReducer, useRef, useState } from 'react'

import { api, type NarrationDirection } from '../../../lib/api'
import type { SpeechSettings, SpeechVoice } from '../../../lib/readAloud'
import { loadSpeechSettings, saveSpeechSettings } from '../../../lib/readAloudSettings'
import { webSpeechEngine } from '../../../lib/webSpeech'
import { Narration } from './narration'

/**
 * Narration bound to the reader screen. Everything it decides is in
 * `Narration`, which has tests; this only hands it the browser's voice, the
 * page on screen and a way to redraw.
 */
export function useNarration(options: {
  chapterId: number
  pageCount: number
  /** The pages on screen, in page order. None is the end of the chapter. */
  pages: number[]
  direction: NarrationDirection
  /** The api has a narrator. */
  available: boolean
  /** The chapter has loaded: until then `pages` says nothing about the end. */
  ready: boolean
  /** Narration was on in the chapter the reader came from. */
  initiallyOn: boolean
  onChange: (on: boolean) => void
  onPagesDone: () => 'continue' | 'end'
}) {
  const [engine] = useState(webSpeechEngine)
  const [, redraw] = useReducer((count: number) => count + 1, 0)
  const [voices, setVoices] = useState<SpeechVoice[]>([])
  const [settings, setSettings] = useState(loadSpeechSettings)
  // A ref, so the narration is built once and still asks for the chapter,
  // direction and page turn of the latest render.
  const latest = useRef(options)
  latest.current = options

  const [narration] = useState(
    () =>
      engine &&
      new Narration(engine, settings, {
        pageCount: () => latest.current.pageCount,
        transcript: (page) =>
          api.readerTranscript(latest.current.chapterId, page, latest.current.direction),
        pagesDone: () => latest.current.onPagesDone(),
        changed: redraw,
      }),
  )

  // Voices arrive after the page does, in Chrome only once asked for.
  useEffect(() => {
    if (!engine) return
    setVoices(engine.voices())
    return engine.onVoicesChanged(() => setVoices(engine.voices()))
  }, [engine])

  useEffect(() => () => narration?.dispose(), [narration])

  const { ready, available, initiallyOn } = options
  const shown = options.pages.join(',')
  useEffect(() => {
    // Before the chapter has loaded there are no pages, and no pages is what
    // the end of a chapter looks like.
    if (ready) narration?.show(shown === '' ? [] : shown.split(',').map(Number))
  }, [narration, ready, shown])

  // Carried over from the previous chapter. The browser lets this speak
  // without a new key press because the reader never left the page.
  const carried = useRef(false)
  useEffect(() => {
    if (!ready || !available || !initiallyOn || !narration || carried.current) return
    carried.current = true
    if (!narration.on) narration.toggle()
  }, [narration, ready, available, initiallyOn])

  const on = narration?.on ?? false
  const reported = useRef(on)
  useEffect(() => {
    if (reported.current === on) return
    reported.current = on
    latest.current.onChange(on)
  }, [on])

  const supported = narration !== null && available
  const toggle = useCallback(() => {
    if (supported && latest.current.ready) narration?.toggle()
  }, [narration, supported])
  const playPause = useCallback(() => narration?.playPause(), [narration])
  const skip = useCallback((delta: number) => narration?.skip(delta), [narration])
  const configure = useCallback(
    (next: SpeechSettings) => {
      setSettings(next)
      saveSpeechSettings(next)
      narration?.configure(next)
    },
    [narration],
  )

  return {
    /** A narrator is set up and this browser can speak. */
    supported,
    on,
    state: narration?.state ?? 'stopped',
    voices,
    settings,
    transcripts: narration?.transcripts ?? null,
    failed: narration?.failed ?? null,
    place: narration?.place ?? null,
    toggle,
    playPause,
    skip,
    configure,
  }
}

export type NarrationView = ReturnType<typeof useNarration>
