import { IconButton } from '../../ui'
import type { PlayState, SpeechSettings, SpeechVoice } from './readAloud'

const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2]

const SELECT =
  'rounded-lg bg-surface-container-low px-space-sm py-space-xs text-body-sm text-on-surface focus:bg-surface-container-high focus:outline-hidden'

/**
 * The player, pinned to the bottom of the page while reading aloud. Apart
 * from the top bar, which steps aside as the text scrolls forward: reading
 * aloud scrolls forward the whole time.
 */
export function ReadAloudBar({
  state,
  voices,
  settings,
  onToggle,
  onSkip,
  onConfigure,
  onClose,
}: {
  state: PlayState
  voices: SpeechVoice[]
  settings: SpeechSettings
  onToggle: () => void
  onSkip: (delta: number) => void
  onConfigure: (next: SpeechSettings) => void
  onClose: () => void
}) {
  const ordered = [...voices].sort(
    (a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name),
  )
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 flex justify-center px-space-sm pb-space-sm">
      <div
        role="region"
        aria-label="Read aloud"
        className="flex w-full max-w-prose-column flex-wrap items-center gap-space-sm rounded-lg bg-surface-container/95 p-space-sm text-on-surface shadow-card"
      >
        <IconButton icon="skip_previous" label="Previous paragraph" onClick={() => onSkip(-1)} />
        <IconButton
          icon={state === 'playing' ? 'pause' : 'play'}
          label={state === 'playing' ? 'Pause' : 'Resume'}
          onClick={onToggle}
        />
        <IconButton icon="skip_next" label="Next paragraph" onClick={() => onSkip(1)} />
        <select
          aria-label="Speed"
          value={String(settings.rate)}
          onChange={(event) => onConfigure({ ...settings, rate: Number(event.target.value) })}
          className={SELECT}
        >
          {RATES.map((rate) => (
            <option key={rate} value={String(rate)}>
              {rate}×
            </option>
          ))}
        </select>
        <select
          aria-label="Voice"
          value={settings.voice ?? ''}
          onChange={(event) => onConfigure({ ...settings, voice: event.target.value || null })}
          className={`min-w-0 flex-1 truncate ${SELECT}`}
        >
          <option value="">Default voice</option>
          {ordered.map((voice) => (
            <option key={voice.id} value={voice.id}>
              {voice.name} ({voice.lang})
            </option>
          ))}
        </select>
        <IconButton icon="close" label="Stop reading aloud" onClick={onClose} />
      </div>
    </div>
  )
}
