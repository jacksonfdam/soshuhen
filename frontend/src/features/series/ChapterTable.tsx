import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Button, Icon } from '../../ui'
import type { SeriesChapter } from '../../lib/api'
import { externalBase } from '../../lib/externalUrl'
import { formatChapter } from '../../lib/format'
import { useUrlState } from '../../lib/useUrlState'

/**
 * How many rows the table shows before the disclosure.
 *
 * The reference render shows four and then "Ver todos os 172 capítulos", which
 * is a mockup's worth of rows rather than a usable one. Twenty is a screenful
 * and it is the same number the download batch uses, so the bounded view is
 * roughly one batch of work. Unbounded, Chainsaw Man's page measured 16 083
 * pixels: every control below the table was off the end of a scroll nobody
 * would finish.
 */
const PREVIEW_ROWS = 20

// Chapter state is a pipeline concept, not a ListStatus, so it gets its own
// small tone map rather than forcing StatusPill's typing to fit a different
// domain — the same reasoning JobRow's JobStateBadge already documents.
const TONE: Record<string, 'secondary' | 'tertiary' | 'error' | 'primary'> = {
  downloaded: 'secondary',
  downloading: 'tertiary',
  queued: 'tertiary',
  known: 'primary',
  failed: 'error',
  skipped: 'primary',
}

const LABEL: Record<string, string> = {
  downloaded: 'Downloaded',
  downloading: 'Downloading',
  queued: 'Queued',
  known: 'Known',
  failed: 'Failed',
  skipped: 'Skipped',
}

// The bracket form is load-bearing: 12 isn't on Tailwind's opacity scale, so a
// plain `/12` modifier compiles to no rule (see StatusPill.tsx).
const TINT: Record<string, string> = {
  secondary: 'bg-secondary/[0.12] text-secondary',
  tertiary: 'bg-tertiary/[0.12] text-tertiary',
  error: 'bg-error/[0.12] text-error',
  primary: 'bg-primary/[0.12] text-primary',
}

function ChapterStateBadge({ state }: { state: string }) {
  const tone = TONE[state] ?? 'primary'
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-space-sm py-0.5 font-mono text-label-sm ${TINT[tone]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {LABEL[state] ?? state}
    </span>
  )
}

// Markup reference: the "Capítulos & Histórico" list in
// .redesign/detalhes_do_mang_gest_o_de_pipeline_sincronia_multi_destino/code.html.
// The reference's release-date column stays dropped — this pipeline has no
// release calendar — but its reader action is now real: Komga is the reader,
// and a chapter it has indexed can be opened straight into it.
type Order = 'newest' | 'oldest'

export function ChapterTable({
  chapters,
  komgaBaseUrl,
  progress,
}: {
  chapters: SeriesChapter[]
  /** Where Komga is served to a browser. Empty means no reader links at all. */
  komgaBaseUrl: string
  /** The furthest chapter any list records as read. Lists count whole
      chapters, so 23.5 is read once progress reaches 24, not at 23. */
  progress: number
}) {
  // Checked here rather than trusted from the prop: this is where the href is
  // built, so this is where a scheme the browser would execute has to stop.
  const komgaHref = externalBase(komgaBaseUrl)
  const [showAll, setShowAll] = useState(false)
  const [order, setOrder] = useUrlState<Order>('order', 'newest', ['newest', 'oldest'])

  if (chapters.length === 0) {
    return (
      <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
        No chapters discovered yet.
      </p>
    )
  }

  const bounded = chapters.length > PREVIEW_ROWS && !showAll
  // Newest first by default: chapter 1 of 313 is the end a reader has already
  // left behind, and it is what the pipeline touched least recently. Oldest
  // first is for starting a series, and its preview is the first chapters.
  const ordered = order === 'newest' ? [...chapters].reverse() : chapters
  const visible = bounded ? ordered.slice(0, PREVIEW_ROWS) : ordered
  // Read is derived, never marked: the lists already know how far reading
  // got, and a second record here would disagree with them by the next sync.
  const isRead = (chapter: SeriesChapter) => chapter.number <= progress
  const next = chapters.find((chapter) => !isRead(chapter))
  // The furthest chapter actually held, not `progress` itself: a series with a
  // gap in its numbering may have no chapter carrying that exact number.
  const lastRead = chapters.filter(isRead).at(-1)
  const edge = order === 'newest' ? 'last' : 'first'

  return (
    <div className="flex flex-col gap-space-sm">
    {/* One button that names the order in force, rather than the segmented
        control: that one drops its labels below sm, and these options have no
        icon to fall back on, so on a phone it rendered two empty pills. */}
    <div className="flex justify-end">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOrder(order === 'newest' ? 'oldest' : 'newest')}
        aria-label={`Sorted ${order} first. Switch order`}
      >
        {order === 'newest' ? 'Newest first' : 'Oldest first'}
      </Button>
    </div>
    <div className="overflow-x-auto rounded-xl bg-surface-container-low shadow-card">
      <table className="w-full min-w-[520px] border-collapse">
        <thead>
          <tr className="border-b border-surface-container-highest/40 text-left font-mono text-label-sm text-outline">
            <th scope="col" className="px-space-md py-space-sm font-normal">Chapter</th>
            <th scope="col" className="px-space-md py-space-sm font-normal">State</th>
            <th scope="col" className="w-0 px-space-md py-space-sm text-right font-normal">
              Read
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((chapter) => {
            const read = isRead(chapter)
            return (
            <tr
              key={chapter.id}
              className="border-b border-surface-container-highest/20 last:border-0 hover:bg-surface-container-high/40"
            >
              {/* The file path moved into this cell's tooltip. It was a column
                  of its own and every row of it was the same directory
                  truncated at the same point, which told the reader nothing
                  three columns could not. */}
              <td
                className="max-w-[1px] px-space-md py-space-sm"
                title={chapter.file_path ?? undefined}
              >
                <div className="flex flex-col">
                  <span
                    className={`inline-flex items-center gap-space-xs text-body-sm font-semibold ${
                      read ? 'text-secondary' : 'text-on-surface'
                    }`}
                  >
                    Ch {formatChapter(chapter.number)}
                    {chapter === lastRead && (
                      <span title="Last chapter read" aria-label="Last chapter read" className="text-tertiary">
                        <Icon name="bookmark" className="h-3.5 w-3.5" />
                      </span>
                    )}
                    {chapter === next && (
                      <span className="rounded-full bg-primary/[0.12] px-space-sm py-0.5 font-mono text-label-sm text-primary">
                        Next
                      </span>
                    )}
                  </span>
                  {chapter.title && (
                    <span
                      className={`truncate font-mono text-label-sm ${
                        read ? 'text-secondary/70' : 'text-outline'
                      }`}
                    >
                      {chapter.title}
                    </span>
                  )}
                </div>
              </td>
              <td className="w-0 whitespace-nowrap px-space-md py-space-sm">
                <ChapterStateBadge state={chapter.state} />
              </td>
              <td className="w-0 whitespace-nowrap px-space-md py-space-sm text-right">
                <div className="inline-flex items-center gap-space-xs">
                  {/* Every chapter can be read now: one not downloaded yet is
                      streamed from its source and saved as it is read. */}
                  <Link
                    to={`/read/${chapter.id}`}
                    className="inline-flex items-center gap-1.5 rounded-lg px-space-sm py-1 font-mono text-label-sm text-primary transition-colors hover:bg-primary/[0.12]"
                  >
                    <Icon name="book" className="h-3.5 w-3.5" />
                    Read
                  </Link>
                  {komgaHref && chapter.komga_book_id && (
                    <a
                      href={`${komgaHref}/book/${chapter.komga_book_id}/read?page=1&incognito=false`}
                      target="_blank"
                      rel="noreferrer"
                      title="Open in Komga"
                      aria-label="Open in Komga"
                      className="inline-flex items-center rounded-lg px-space-xs py-1 text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
                    >
                      <Icon name="link" className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              </td>
            </tr>
            )
          })}
        </tbody>
      </table>
    </div>
      {chapters.length > PREVIEW_ROWS && (
        <div className="flex items-center gap-space-md">
          <Button
            variant="surface"
            icon="chevron"
            aria-expanded={showAll}
            onClick={() => setShowAll(!showAll)}
          >
            {showAll ? `Show the ${edge} ${PREVIEW_ROWS}` : `Show all ${chapters.length} chapters`}
          </Button>
          {bounded && (
            <span className="font-mono text-label-sm text-outline">
              Showing the {edge} {PREVIEW_ROWS} of {chapters.length}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
