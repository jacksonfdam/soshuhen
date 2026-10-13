import { Link } from 'react-router-dom'

import type { ReaderManifest } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { Icon, type IconName } from '../../ui'
import { PageSlider } from './PageSlider'
import type { Panel } from './ReaderPage'

const TOOL =
  'inline-flex h-10 w-10 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface disabled:opacity-40'

function ToolButton({
  icon,
  label,
  disabled = false,
  onClick,
}: {
  icon: IconName
  label: string
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={TOOL}
    >
      <Icon name={icon} className="h-5 w-5" />
    </button>
  )
}

/** xl and above, after MangaDex: always on screen and out of the page's way. */
export function DesktopChrome({
  manifest,
  page,
  rtl,
  strip,
  onSeek,
  onOpenChapter,
  onPanel,
  onFullscreen,
}: {
  manifest: ReaderManifest
  page: number
  rtl: boolean
  strip: boolean
  onSeek: (page: number) => void
  onOpenChapter: (chapterId: number) => void
  onPanel: (panel: Panel) => void
  onFullscreen: () => void
}) {
  const { chapter, previous, next } = manifest
  return (
    <div className="hidden xl:block">
      <div className="fixed left-1/2 top-space-md z-30 flex -translate-x-1/2 items-center gap-space-sm rounded-full bg-surface-container/90 px-space-sm py-space-xs shadow-card">
        <ToolButton
          icon="chevron_left"
          label={strip ? "Previous chapter (← or [)" : "Previous chapter ([)"}
          disabled={!previous}
          onClick={() => previous && onOpenChapter(previous.id)}
        />
        <span className="font-mono text-label-md text-on-surface">
          Ch. {formatChapter(chapter.number)}
        </span>
        <ToolButton
          icon="chevron_right"
          label={strip ? "Next chapter (→ or ])" : "Next chapter (])"}
          disabled={!next}
          onClick={() => next && onOpenChapter(next.id)}
        />
      </div>

      <nav className="fixed right-space-md top-1/2 z-30 flex -translate-y-1/2 flex-col gap-space-xs rounded-lg bg-surface-container/90 p-space-xs shadow-card">
        <Link to="/" aria-label="Home" title="Home" className={TOOL}>
          <Icon name="home" className="h-5 w-5" />
        </Link>
        <Link to={`/series/${manifest.series.id}`} aria-label="Series" title="Series" className={TOOL}>
          <Icon name="book" className="h-5 w-5" />
        </Link>
        <ToolButton icon="list" label="Chapters" onClick={() => onPanel('chapters')} />
        <ToolButton icon="settings" label="Reader settings" onClick={() => onPanel('settings')} />
        <ToolButton icon="fullscreen" label="Fullscreen (f)" onClick={onFullscreen} />
      </nav>

      {manifest.origin === 'stream' && (
        <p className="fixed left-space-md top-space-md z-30 max-w-xs rounded-lg bg-surface-container/90 px-space-sm py-space-xs text-body-sm text-on-surface-variant">
          Streaming from the source. Saved to the library once every page has loaded.
        </p>
      )}

      {!strip && (
        <div className="fixed bottom-space-md left-1/2 z-30 w-full max-w-xl -translate-x-1/2">
          <PageSlider page={page} pageCount={manifest.page_count} rtl={rtl} onSeek={onSeek} />
        </div>
      )}
    </div>
  )
}
