import type { SpeechEngine, SpeechVoice } from './readAloud'

/** The browser's own voices, or null where the browser has none to offer. */
export function webSpeechEngine(): SpeechEngine | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null
  const synth = window.speechSynthesis
  // Chrome lets an utterance nobody references be collected mid-sentence, and
  // its end event then never fires; holding it here keeps it alive.
  let current: SpeechSynthesisUtterance | null = null

  const voices = (): SpeechVoice[] =>
    synth.getVoices().map((voice) => ({ id: voice.voiceURI, name: voice.name, lang: voice.lang }))

  return {
    voices,
    onVoicesChanged(listener) {
      synth.addEventListener('voiceschanged', listener)
      return () => synth.removeEventListener('voiceschanged', listener)
    },
    speak(text, settings, done) {
      const utterance = new SpeechSynthesisUtterance(text)
      const voice = synth.getVoices().find((option) => option.voiceURI === settings.voice)
      if (voice) {
        utterance.voice = voice
        utterance.lang = voice.lang
      }
      utterance.rate = settings.rate
      let reported = false
      const report = (finished: boolean) => {
        if (reported) return
        reported = true
        if (current === utterance) current = null
        done(finished)
      }
      utterance.onend = () => report(true)
      utterance.onerror = () => report(false)
      current = utterance
      // A pause left over from another page would hold every new utterance.
      if (synth.paused) synth.resume()
      synth.speak(utterance)
    },
    cancel() {
      synth.cancel()
    },
  }
}
