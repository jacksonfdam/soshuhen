import { useState } from 'react'

import { Badge, Button, Card, Icon } from '../../ui'
import { messageOf } from '../../lib/api'
import type { SeriesVolume } from '../../lib/api'
import { externalBase } from '../../lib/externalUrl'

// The volumes the user owns: from J-Novel Club, which download by themselves -
// buying one is the decision - or imported from their own PDFs. The panel only
// reports where each stands.
function stateBadge(volume: SeriesVolume) {
  if (volume.status === 'preorder') return <Badge tone="tertiary">Pre-order</Badge>
  if (volume.state === 'downloaded') return <Badge tone="secondary">Downloaded</Badge>
  // Offloaded on the user's word: a revision waits for them instead of
  // downloading by itself, so the badge says there is one.
  if (volume.state === 'offloaded') {
    return (
      <Badge tone="secondary">
        {volume.revised ? 'On device · newer revision on J-Novel Club' : 'On device'}
      </Badge>
    )
  }
  if (volume.state === 'failed') return <Badge tone="error">Failed</Badge>
  if (volume.revised) return <Badge tone="warning">Updated, downloading again</Badge>
  if (volume.state === 'queued' || volume.state === 'downloading') {
    return <Badge tone="primary">Queued</Badge>
  }
  // known: no download waiting. The next library sync queues it; saying
  // "Queued" here would be a promise nothing is keeping.
  return <Badge tone="tertiary">Not downloaded yet</Badge>
}

function DownloadAgain({ volumeId, onDownload }: { volumeId: number; onDownload: (id: number) => Promise<unknown> }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const click = () => {
    setBusy(true)
    setError(null)
    onDownload(volumeId)
      .catch((failure: unknown) => setError(messageOf(failure)))
      .finally(() => setBusy(false))
  }
  return (
    <>
      <Button variant="ghost" size="sm" icon="download" onClick={click} disabled={busy}>
        Download again
      </Button>
      {error && <span className="text-label-sm text-error">{error}</span>}
    </>
  )
}

export function VolumesPanel({
  volumes,
  komgaBaseUrl,
  onDownloadAgain,
}: {
  volumes: SeriesVolume[]
  komgaBaseUrl: string
  onDownloadAgain?: (volumeId: number) => Promise<unknown>
}) {
  const komgaHref = externalBase(komgaBaseUrl)
  if (volumes.length === 0) return null
  // Named only when one number holds both editions; otherwise it is noise.
  const numbers = volumes.map((volume) => volume.number)
  const twice = new Set(numbers.filter((n, i) => numbers.indexOf(n) !== i))
  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <h2 className="text-title-md text-on-surface">Volumes</h2>
      <ul className="flex flex-col gap-space-xs">
        {volumes.map((volume) => (
          <li key={`${volume.number}-${volume.edition}`} className="flex flex-wrap items-center justify-between gap-space-sm">
            <span className="text-body-sm text-on-surface">
              Vol. {volume.number}
              {twice.has(volume.number) && (
                <span className="text-on-surface-variant">
                  {' '}
                  · {volume.edition === 'light' ? 'Light novel' : 'Web novel'}
                </span>
              )}
              {volume.title && <span className="text-on-surface-variant"> · {volume.title}</span>}
            </span>
            <span className="inline-flex items-center gap-space-xs">
              {stateBadge(volume)}
              {onDownloadAgain && volume.id != null && volume.state === 'offloaded' && (
                <DownloadAgain volumeId={volume.id} onDownload={onDownloadAgain} />
              )}
              {komgaHref && volume.komga_book_id && volume.state === 'downloaded' && (
                <a
                  href={`${komgaHref}/book/${volume.komga_book_id}/read-epub`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg px-space-sm py-1 font-mono text-label-sm text-primary transition-colors hover:bg-primary/[0.12]"
                >
                  <Icon name="book" className="h-3.5 w-3.5" />
                  Read in Komga
                </a>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
