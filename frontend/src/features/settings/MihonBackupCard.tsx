import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api, messageOf, type MihonImport, type MihonImportItem } from '../../lib/api'
import { Button, buttonClass, Icon } from '../../ui'

const ACTION_LABEL: Record<MihonImportItem['action'], string> = {
  map: 'Takes this source',
  same: 'Already reads from it',
  kept: 'Left as it is',
  unmatched: 'Not in your library',
}

const ACTION_TONE: Record<MihonImportItem['action'], string> = {
  map: 'text-secondary',
  same: 'text-on-surface-variant',
  kept: 'text-warning',
  unmatched: 'text-outline',
}

/**
 * Moving between Soshuhen and Mihon, in both directions.
 *
 * An import is always read first and shown, then applied on a second click
 * with the same file: it confirms source mappings without the review step,
 * and that is only acceptable as a decision the reader looked at.
 */
export function MihonBackupCard() {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<MihonImport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const read = async (next: File, apply: boolean) => {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.importMihon(next, apply))
    } catch (failure) {
      setError(messageOf(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-space-md rounded-xl bg-surface-container p-space-lg shadow-card">
      <div className="flex flex-col gap-space-xs">
        <h3 className="text-title-md font-semibold text-on-surface">Mihon backup</h3>
        <p className="text-body-sm text-on-surface-variant">
          Export every series with a source as a <code className="font-mono">.tachibk</code> file
          Mihon restores, with chapters read up to your lists and your bookmarks. Import one to give
          series that have no source yet the one you read them from in Mihon.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-space-sm">
        <a href="/api/backup/mihon" download className={buttonClass({ size: 'sm' })}>
          <Icon name="download" className="h-4 w-4" />
          Export
        </a>
        <label className={`${buttonClass({ size: 'sm' })} cursor-pointer`}>
          <Icon name="folder" className="h-4 w-4" />
          Read a backup…
          <input
            type="file"
            accept=".tachibk,.proto.gz,application/octet-stream"
            className="sr-only"
            onChange={(event) => {
              const chosen = event.target.files?.[0]
              event.target.value = ''
              if (!chosen) return
              setFile(chosen)
              setResult(null)
              void read(chosen, false)
            }}
          />
        </label>
      </div>

      {busy && <p className="text-body-sm text-on-surface-variant">Reading…</p>}
      {error && <p className="text-body-sm text-error">{error}</p>}

      {result && file && (
        <div className="flex flex-col gap-space-sm">
          <p className="text-body-sm text-on-surface">
            {result.applied ? 'Imported' : 'Read'} {result.titles} titles from {file.name}:{' '}
            {(Object.keys(ACTION_LABEL) as MihonImportItem['action'][])
              .filter((action) => result.counts[action])
              .map((action) => `${result.counts[action]} ${ACTION_LABEL[action].toLowerCase()}`)
              .join(' · ')}
          </p>
          <ul className="flex max-h-80 flex-col gap-space-xs overflow-y-auto rounded-lg bg-surface-container-low p-space-sm">
            {result.items.map((item, index) => (
              <li key={`${item.title}-${index}`} className="flex flex-col">
                <span className="flex items-center justify-between gap-space-sm">
                  {item.series_id !== null ? (
                    <Link to={`/series/${item.series_id}`} className="truncate text-body-sm text-on-surface hover:underline">
                      {item.title}
                    </Link>
                  ) : (
                    <span className="truncate text-body-sm text-on-surface-variant">{item.title}</span>
                  )}
                  <span className={`shrink-0 font-mono text-label-sm ${ACTION_TONE[item.action]}`}>
                    {ACTION_LABEL[item.action]}
                  </span>
                </span>
                <span className="truncate font-mono text-label-sm text-outline">
                  {[item.source_site, item.matched_by, item.reason, item.bookmarks ? `${item.bookmarks} bookmarks` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </li>
            ))}
          </ul>
          {!result.applied && (
            <div className="flex items-center gap-space-sm">
              <Button
                variant="primary"
                size="sm"
                disabled={busy || !result.items.some((item) => item.series_id !== null)}
                onClick={() => void read(file, true)}
              >
                Import
              </Button>
              <span className="text-body-sm text-on-surface-variant">
                Bookmarks are copied to chapters already listed here.
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
