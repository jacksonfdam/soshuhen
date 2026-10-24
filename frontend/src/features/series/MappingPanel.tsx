import { useCallback, useEffect, useState } from 'react'

import { Button, CandidateList, Card, Icon, Skeleton, type SourceChoice } from '../../ui'
import { api, messageOf, type MappingPreview } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { useJobEvents } from '../../lib/useEvents'
import { PROVIDER_LABEL } from '../../lib/format'

// Markup reference: the "Pipeline & Mapeamento" block in
// .redesign/detalhes_do_mang_gest_o_de_pipeline_sincronia_multi_destino/code.html.
// The reference shows a MangaDex UUID, a mirror list and a ComicInfo.xml
// verification badge — none of which the API returns (the mapping is one
// source_site/source_url pair, nothing else) — so this shows only that pair
// and the action that requests a new one.
export function MappingPanel({
  seriesId,
  mapping,
  local = false,
  onResearch,
  onRemap,
}: {
  seriesId: number
  mapping: { source_site: string; source_url: string } | null
  /** Already in the library with no source: a mapping is optional, not awaited. */
  local?: boolean
  onResearch: () => Promise<unknown>
  /** Supersede the mapping with a URL typed by hand. */
  onRemap: (sourceUrl: string) => Promise<unknown>
}) {
  const [status, setStatus] = useState<'idle' | 'busy' | 'queued'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [candidates, setCandidates] = useState<SourceChoice[] | null>(null)
  // A local series reads fine as it is. Candidates parked by an old search stay
  // stored, but are shown only once the reader asks to look for a source.
  const [looking, setLooking] = useState(false)
  const quiet = local && !mapping && !looking
  // A move away from a mapped source is compared before it is made. The first
  // mapping has nothing to compare with and is confirmed straight away.
  const [move, setMove] = useState<{
    url: string
    preview: MappingPreview | null
    error: string | null
  } | null>(null)

  const loadCandidates = useCallback(() => {
    api
      .candidates(seriesId)
      .then((payload) =>
        setCandidates(
          payload.candidates.map((c) => ({
            url: c.source_url,
            site: c.source_site,
            score: c.score,
            title: c.title,
            cover_url: c.cover_url,
            chapters: c.chapter_count,
            year: c.year,
          })),
        ),
      )
      .catch(() => setCandidates([]))
  }, [seriesId])

  useEffect(loadCandidates, [loadCandidates])

  // The search is a job, and the candidates land when it finishes. Without
  // this the reader queues a search, is told it is queued, and has to reload
  // the page to find out it found anything — which is exactly the complaint
  // the Review screen used to draw.
  useJobEvents((event) => {
    if (event.event !== 'job.progress') loadCandidates()
  })

  const compare = (url: string) => {
    setMove({ url, preview: null, error: null })
    setError(null)
    api
      .previewMapping(seriesId, url)
      .then((preview) => setMove((current) => (current?.url === url ? { ...current, preview } : current)))
      .catch((failure: unknown) =>
        setMove((current) =>
          current?.url === url ? { ...current, error: messageOf(failure) } : current,
        ),
      )
  }

  const save = async () => {
    if (draft === null) return
    const url = draft.trim()
    if (!url || url === mapping?.source_url) {
      setDraft(null)
      return
    }
    if (mapping) {
      setDraft(null)
      compare(url)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onRemap(url)
      setDraft(null)
    } catch (err) {
      // The address stays in the box on a refusal. The API rejects a URL no
      // source owns, and retyping it from memory is the last thing someone
      // whose paste was just rejected wants to do.
      setError(messageOf(err))
    } finally {
      setSaving(false)
    }
  }

  /** Taking a candidate is the same act as pasting its address, so it takes
      the same path — one refusal message, one reload, one place to change. */
  const confirm = async (url: string) => {
    setSaving(true)
    setError(null)
    try {
      await onRemap(url)
      setMove(null)
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setSaving(false)
    }
  }

  const research = async () => {
    setStatus('busy')
    setError(null)
    try {
      await onResearch()
      setStatus('queued')
    } catch (err) {
      // Reverting the button label without saying why reads as broken, not
      // declined — the download-range form already surfaces its own
      // rejection text, and this control has to match it.
      setStatus('idle')
      setError(messageOf(err))
    }
  }

  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <div className="flex items-center gap-space-xs">
        <Icon name="link" className="h-4 w-4 text-primary" />
        <h2 className="text-title-md text-on-surface">Source mapping</h2>
      </div>
      {draft !== null ? (
        <div className="flex flex-col gap-space-xs">
          <label className="font-mono text-label-sm text-outline" htmlFor="mapping-url">
            Source URL
          </label>
          <input
            id="mapping-url"
            value={draft}
            autoFocus
            spellCheck={false}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void save()
              if (event.key === 'Escape') setDraft(null)
            }}
            placeholder="https://mangadex.org/title/..."
            className="w-full rounded-lg bg-surface-container-highest px-space-sm py-2 font-mono text-body-sm text-on-surface outline-hidden ring-1 ring-outline-variant/40 focus:ring-primary"
          />
          {/* Said before the button is pressed: this is not an edit to a label,
              it re-reads the chapter list from the new source. */}
          <p className="text-body-sm text-on-surface-variant">
            Confirming supersedes the current mapping and re-runs chapter discovery.
          </p>
          <div className="flex items-center gap-space-xs">
            <Button variant="primary" size="sm" disabled={saving} onClick={save}>
              {saving ? 'Confirming…' : 'Confirm'}
            </Button>
            <Button variant="surface" size="sm" disabled={saving} onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : mapping ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-label-sm text-outline">
            {PROVIDER_LABEL[mapping.source_site] ?? mapping.source_site}
          </span>
          <a
            href={mapping.source_url}
            target="_blank"
            rel="noreferrer"
            className="truncate text-body-sm text-primary hover:underline"
          >
            {mapping.source_url}
          </a>
        </div>
      ) : local ? (
        <p className="text-body-sm text-on-surface-variant">
          Reads from files already in your library. A source is only needed to download more.
        </p>
      ) : (
        <p className="text-body-sm text-on-surface-variant">
          No source mapped yet — downloads cannot start until one is confirmed.
        </p>
      )}
      {quiet && draft === null && (
        <Button
          variant="surface"
          size="sm"
          icon="sync"
          onClick={() => setLooking(true)}
          className="w-fit"
        >
          Find a source
        </Button>
      )}

      {/* Shown whether or not a mapping exists: re-running the search on a
          mapped series is how a wrong mapping gets corrected, and parking the
          results somewhere the reader cannot see them is what made that
          impossible. */}
      {quiet ? null : candidates === null ? (
        <Skeleton className="h-12 w-full" />
      ) : candidates.length > 0 ? (
        <div className="flex flex-col gap-space-xs">
          <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
            {mapping ? 'Other sources found' : 'Sources found'}
          </span>
          <CandidateList
            candidates={candidates.filter((c) => c.url !== mapping?.source_url)}
            busy={saving}
            onChoose={(candidate) =>
              mapping ? compare(candidate.url) : void confirm(candidate.url)
            }
          />
        </div>
      ) : null}
      {move && (
        <MoveComparison
          url={move.url}
          preview={move.preview}
          error={move.error}
          busy={saving}
          onConfirm={() => void confirm(move.url)}
          onCancel={() => setMove(null)}
        />
      )}
      {!quiet && draft === null && move === null && (
        <div className="flex flex-wrap items-center gap-space-xs">
          <Button
            variant="surface"
            size="sm"
            icon="sync"
            disabled={status === 'busy'}
            onClick={research}
            className="w-fit"
          >
            {status === 'queued' ? 'Search queued' : mapping ? 'Re-run search' : 'Find a source'}
          </Button>
          {/* The search parks candidates and waits for a decision, which is the
              right default. This is the way out when no candidate is the right
              one and the reader already knows the address. */}
          <Button
            variant="surface"
            size="sm"
            icon="link"
            onClick={() => setDraft(mapping?.source_url ?? '')}
            className="w-fit"
          >
            {mapping ? 'Edit source' : 'Paste a URL'}
          </Button>
        </div>
      )}
      {error && <p className="font-mono text-label-sm text-error">{error}</p>}
    </Card>
  )
}

function MoveComparison({
  url,
  preview,
  error,
  busy,
  onConfirm,
  onCancel,
}: {
  url: string
  preview: MappingPreview | null
  error: string | null
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const lines = preview
    ? [
        `${preview.chapters} chapters there${preview.last !== null ? `, up to ${formatChapter(preview.last)}` : ''}${
          preview.current_last !== null ? ` (here: up to ${formatChapter(preview.current_last)})` : ''
        }.`,
        preview.gained > 0 ? `${preview.gained} chapters not known here yet.` : null,
        preview.retried > 0 ? `${preview.retried} that failed here will be tried again from it.` : null,
        preview.set_aside > 0
          ? `${preview.set_aside} not downloaded and not listed there will be set aside.`
          : null,
        preview.downloaded > 0 ? `${preview.downloaded} already in the library stay as they are.` : null,
        'Reading progress and list entries stay as they are: they count chapters by number.',
      ].filter((line): line is string => line !== null)
    : []

  return (
    <div className="flex flex-col gap-space-sm rounded-lg bg-surface-container-low p-space-md">
      <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
        Move to {preview?.source_site ?? 'another source'}
      </span>
      <span className="truncate font-mono text-label-sm text-on-surface-variant">{url}</span>
      {error ? (
        <p className="text-body-sm text-error">{error}</p>
      ) : !preview ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <>
          {preview.stops_before_progress && (
            // The one outcome that defeats the usual reason for moving.
            <p className="rounded-lg bg-warning-container/30 px-space-sm py-space-xs text-body-sm text-on-surface">
              It stops at chapter {formatChapter(preview.last ?? 0)}, before chapter{' '}
              {formatChapter(preview.progress)}, where your reading got to.
            </p>
          )}
          <ul className="flex flex-col gap-space-xs">
            {lines.map((line) => (
              <li key={line} className="text-body-sm text-on-surface-variant">
                {line}
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="flex items-center gap-space-xs">
        <Button variant="primary" size="sm" disabled={busy || !preview} onClick={onConfirm}>
          {busy ? 'Moving…' : 'Move'}
        </Button>
        <Button variant="surface" size="sm" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}
