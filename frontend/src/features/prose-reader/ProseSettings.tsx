import type { ProsePrefs } from '../../lib/api'
import { IconButton, ReaderSheet } from '../../ui'
import { LARGEST, SMALLEST, THEMES } from './theme'

export function ProseSettings({
  prefs,
  error,
  onChange,
  onClose,
}: {
  prefs: ProsePrefs
  error: string | null
  onChange: (next: ProsePrefs) => void
  onClose: () => void
}) {
  const { font_size: size, theme } = prefs
  return (
    <ReaderSheet title="Reading settings" onClose={onClose}>
      <fieldset className="flex flex-col pt-space-md">
        <legend className="pb-space-sm text-label-md text-on-surface-variant">Text size</legend>
        <div className="flex items-center gap-space-md">
          <IconButton
            icon="chevron_left"
            label="Smaller text"
            disabled={size <= SMALLEST}
            onClick={() => onChange({ font_size: size - 1, theme })}
          />
          <span className="min-w-space-xl text-center font-mono text-title-md text-on-surface">
            {size}
          </span>
          <IconButton
            icon="chevron_right"
            label="Larger text"
            disabled={size >= LARGEST}
            onClick={() => onChange({ font_size: size + 1, theme })}
          />
        </div>
      </fieldset>
      <fieldset className="flex flex-col pt-space-md">
        <legend className="pb-space-sm text-label-md text-on-surface-variant">Background</legend>
        <div className="flex flex-wrap gap-space-sm">
          {THEMES.map((option) => {
            const selected = option.value === theme
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={selected}
                onClick={() => onChange({ font_size: size, theme: option.value })}
                className={`rounded-lg border px-space-md py-space-sm text-body-md transition-colors ${
                  selected
                    ? 'border-primary bg-primary/[0.12] text-primary'
                    : 'border-outline-variant text-on-surface hover:bg-surface-container-high'
                }`}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </fieldset>
      <p className="mt-space-lg border-t border-outline-variant pt-space-md text-body-sm text-on-surface-variant">
        Used for every novel.
      </p>
      {error && <p className="mt-space-sm text-body-sm text-error">{error}</p>}
    </ReaderSheet>
  )
}
