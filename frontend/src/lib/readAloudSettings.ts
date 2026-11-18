import type { SpeechSettings } from './readAloud'

// One key for every reader that speaks: a voice and a speed chosen while
// reading a novel are the ones a comic is read in, and the other way round.
const KEY = 'reader:read-aloud'
const DEFAULT: SpeechSettings = { voice: null, rate: 1 }

/** Per device rather than per account: voices differ between browsers. */
export function loadSpeechSettings(): SpeechSettings {
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

export function saveSpeechSettings(settings: SpeechSettings) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    // A private window refuses storage; the choice lasts until the tab closes.
  }
}
