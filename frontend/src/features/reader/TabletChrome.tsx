import { Link } from 'react-router-dom'

import type { ReaderManifest } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { Icon } from '../../ui'
import { PageSlider } from './PageSlider'
import type { Panel } from './ReaderPage'

const ROUND =
  'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-surface-container-highest text-on-surface disabled:opacity-40'

const BAR_BUTTON = 'rounded-lg p-space-sm text-on-surface'

/** Below xl, after Mihon: hidden until a tap in the middle of the page. */
export function TabletChrome({
  manifest,
  page,
  rtl,
  visible,
  onSeek,
  onOpenChapter,
  onPanel,
}: {
  manifest: ReaderManifest
  page: number
  rtl: boolean
  visible: boolean
  onSeek: (page: number) => void
  onOpenChapter: (chapterId: number) => void
  onPanel: (panel: Panel) => void
}) {
  if (!visible) return null
  const { chapter, previous, next } = manifest
  return (
    <div className="xl:hidden">
      <header className="fixed inset-x-0 top-0 z-30 flex items-center gap-space-md bg-surface-container/95 px-space-md py-space-sm">
        <Link
          to={`/series/${manifest.series.id}`}
          aria-label="Back to the series"
          className="rounded-lg p-space-xs text-on-surface"
        >
          <Icon name="arrow_back" className="h-6 w-6" />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="truncate text-title-md text-on-surface">{manifest.series.title}</p>
          <p className="truncate text-body-sm text-on-surface-variant">
            Ch. {formatChapter(chapter.number)}
            {chapter.title ? ` - ${chapter.title}` : ''}
          </p>
        </div>
      </header>
      <footer className="fixed inset-x-0 bottom-0 z-30 flex flex-col gap-space-sm bg-surface-container/95 px-space-md pb-space-md pt-space-sm">
        {manifest.origin === 'stream' && (
          <p className="text-center text-body-sm text-on-surface-variant">
            Streaming from the source. Saved to the library once every page has loaded.
          </p>
        )}
        <div className="flex items-center gap-space-sm">
          <button
            type="button"
            aria-label="Previous chapter"
            disabled={!previous}
            onClick={() => previous && onOpenChapter(previous.id)}
            className={ROUND}
          >
            <Icon name="chevron_left" className="h-5 w-5" />
          </button>
          <PageSlider page={page} pageCount={manifest.page_count} rtl={rtl} onSeek={onSeek} />
          <button
            type="button"
            aria-label="Next chapter"
            disabled={!next}
            onClick={() => next && onOpenChapter(next.id)}
            className={ROUND}
          >
            <Icon name="chevron_right" className="h-5 w-5" />
          </button>
        </div>
        <div className="flex justify-around">
          <button type="button" aria-label="Chapters" onClick={() => onPanel('chapters')} className={BAR_BUTTON}>
            <Icon name="list" className="h-6 w-6" />
          </button>
          <button
            type="button"
            aria-label="Reader settings"
            onClick={() => onPanel('settings')}
            className={BAR_BUTTON}
          >
            <Icon name="settings" className="h-6 w-6" />
          </button>
        </div>
      </footer>
    </div>
  )
}
