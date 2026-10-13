import { useState } from 'react'

import type { ReaderBackground, ReaderMode, ReaderPrefs, ReaderScale } from '../../lib/api'
import { Button, Tabs } from '../../ui'
import { ReaderSheet } from './ReaderSheet'

type Display = Omit<ReaderPrefs, 'custom'>

const MODES: { value: ReaderMode; label: string }[] = [
  { value: 'paged_rtl', label: 'Paged (right to left)' },
  { value: 'paged_ltr', label: 'Paged (left to right)' },
  { value: 'double', label: 'Double page' },
  { value: 'long_strip', label: 'Long strip' },
]

const SCALES: { value: ReaderScale; label: string }[] = [
  { value: 'fit_screen', label: 'Fit screen' },
  { value: 'fit_width', label: 'Fit width' },
  { value: 'fit_height', label: 'Fit height' },
]

const BACKGROUNDS: { value: ReaderBackground; label: string }[] = [
  { value: 'black', label: 'Black' },
  { value: 'gray', label: 'Gray' },
  { value: 'white', label: 'White' },
]

function OptionGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <fieldset className="flex flex-col pt-space-md">
      <legend className="pb-space-sm text-label-md text-on-surface-variant">{label}</legend>
      <div className="flex flex-wrap gap-space-sm">
        {options.map((option) => {
          const selected = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(option.value)}
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
  )
}

export function SettingsPanel({
  prefs,
  error,
  onChange,
  onMakeDefault,
  onClose,
}: {
  prefs: ReaderPrefs
  error: string | null
  onChange: (next: Display) => void
  onMakeDefault: () => void
  onClose: () => void
}) {
  const [tab, setTab] = useState<'layout' | 'image'>('layout')
  const { mode, scale, background } = prefs

  return (
    <ReaderSheet title="Reader settings" onClose={onClose}>
      <Tabs
        options={[
          { value: 'layout', label: 'Layout' },
          { value: 'image', label: 'Image' },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'layout' ? (
        <OptionGroup
          label="Reading mode"
          options={MODES}
          value={mode}
          onChange={(next) => onChange({ mode: next, scale, background })}
        />
      ) : (
        <>
          <OptionGroup
            label="Scale"
            options={SCALES}
            value={scale}
            onChange={(next) => onChange({ mode, scale: next, background })}
          />
          <OptionGroup
            label="Background"
            options={BACKGROUNDS}
            value={background}
            onChange={(next) => onChange({ mode, scale, background: next })}
          />
        </>
      )}
      <div className="mt-space-lg flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant pt-space-md">
        <p className="text-body-sm text-on-surface-variant">
          {prefs.custom ? 'Saved for this series.' : 'Following the default for every series.'}
        </p>
        <Button size="sm" onClick={onMakeDefault}>
          Use for every series
        </Button>
      </div>
      {error && <p className="mt-space-sm text-body-sm text-error">{error}</p>}
    </ReaderSheet>
  )
}
