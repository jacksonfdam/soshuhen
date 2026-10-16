import { useState } from 'react'

import { Card, SegmentedControl } from '../../ui'

type Kind = 'comic' | 'prose'

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

// What decides which sources a series is searched against and which file it
// is downloaded as. Most series never need it - the list providers say - and
// it is here for the ones whose provider said nothing or said it wrong.
export function KindControl({
  kind,
  onChange,
}: {
  kind: Kind | null
  onChange: (kind: Kind) => Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)

  const choose = (next: Kind) => {
    setError(null)
    onChange(next).catch((failure: unknown) => setError(messageOf(failure)))
  }

  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <h2 className="text-title-md text-on-surface">Format</h2>
      {/* Icons because the control drops its labels below sm. */}
      <SegmentedControl<Kind>
        options={[
          { value: 'comic', icon: 'grid', label: 'Comic' },
          { value: 'prose', icon: 'book', label: 'Light novel' },
        ]}
        value={kind ?? 'comic'}
        onChange={choose}
      />
      {error && <p className="font-mono text-label-sm text-error">{error}</p>}
    </Card>
  )
}
