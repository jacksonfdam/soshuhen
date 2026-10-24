import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Icon } from '../../ui'
import type { SeriesChapter, SeriesVolume } from '../../lib/api'
import { formatChapter } from '../../lib/format'

// A novel is read by the volume, so its page lists volumes rather than the
// chapter table: a light novel volume is one book, and a web novel volume is a
// range of chapters that opens to them. A J-Novel Club volume is both: one book
// that also collects the parts released before it. Read is derived from the
// lists, as the chapter table derives it, never marked here.

const READ_LINK =
  'inline-flex items-center gap-1.5 rounded-lg px-space-sm py-1 font-mono text-label-sm text-primary transition-colors hover:bg-primary/[0.12]'

/** A title that only restates the number ("Volume 2" on volume 2) is no title. */
function ownTitle(title: string | null, number: number): string | null {
  if (!title) return null
  return new RegExp(`^vol(ume)?\\.?\\s*0*${number}$`, 'i').test(title.trim()) ? null : title
}

function ReadMark({ read }: { read: boolean }) {
  if (!read) return null
  return (
    <span title="Read" aria-label="Read" className="text-secondary">
      <Icon name="check" className="h-3.5 w-3.5" />
    </span>
  )
}

function NotHere() {
  // Only a file on disk opens; saying why the button is missing beats a gap.
  return <span className="font-mono text-label-sm text-outline">Not in the library</span>
}

function ChapterRow({
  chapter,
  read,
  onBookmark,
}: {
  chapter: SeriesChapter
  read: boolean
  onBookmark: (chapterId: number, bookmarked: boolean) => void
}) {
  return (
    <li className="flex items-center justify-between gap-space-sm py-space-xs pl-space-lg">
      <span className="flex min-w-0 items-center gap-space-xs">
        <span className={`shrink-0 text-body-sm ${read ? 'text-secondary' : 'text-on-surface'}`}>
          Ch {formatChapter(chapter.number)}
        </span>
        {chapter.title && (
          <span className="truncate font-mono text-label-sm text-outline">{chapter.title}</span>
        )}
        <ReadMark read={read} />
      </span>
      <span className="inline-flex shrink-0 items-center gap-space-xs">
        <button
          type="button"
          aria-pressed={chapter.bookmarked}
          aria-label={chapter.bookmarked ? 'Remove bookmark' : 'Bookmark'}
          title={chapter.bookmarked ? 'Remove bookmark' : 'Bookmark'}
          onClick={() => onBookmark(chapter.id, !chapter.bookmarked)}
          className={`inline-flex items-center rounded-lg px-space-xs py-1 transition-colors hover:bg-surface-container-high ${
            chapter.bookmarked ? 'text-warning' : 'text-outline/40 hover:text-on-surface'
          }`}
        >
          <Icon name="star" className="h-3.5 w-3.5" />
        </button>
        {chapter.readable ? (
          <Link to={`/read/prose/chapter/${chapter.id}`} className={READ_LINK}>
            <Icon name="book" className="h-3.5 w-3.5" />
            Read
          </Link>
        ) : (
          <NotHere />
        )}
      </span>
    </li>
  )
}

function VolumeRow({
  volume,
  chapters,
  read,
  isChapterRead,
  startOpen,
  onBookmark,
}: {
  volume: SeriesVolume
  chapters: SeriesChapter[]
  read: boolean
  isChapterRead: (chapter: SeriesChapter) => boolean
  startOpen: boolean
  onBookmark: (chapterId: number, bookmarked: boolean) => void
}) {
  const [open, setOpen] = useState(startOpen)
  const web = volume.edition === 'web'
  const expands = chapters.length > 0
  const range =
    volume.first_part !== null && volume.last_part !== null
      ? `Ch ${formatChapter(volume.first_part)}–${formatChapter(volume.last_part)}`
      : null

  return (
    <li className="flex flex-col border-b border-surface-container-highest/20 last:border-0">
      <div className="flex items-center justify-between gap-space-sm px-space-md py-space-sm">
        <span className="flex min-w-0 items-center gap-space-xs">
          {expands && (
            <button
              type="button"
              aria-expanded={open}
              aria-label={open ? 'Hide chapters' : 'Show chapters'}
              onClick={() => setOpen(!open)}
              className="rounded-lg p-1 text-outline hover:bg-surface-container-high hover:text-on-surface"
            >
              <Icon
                name="chevron"
                className={`h-4 w-4 transition-transform ${open ? '' : '-rotate-90'}`}
              />
            </button>
          )}
          <span
            className={`shrink-0 text-body-sm font-semibold ${read ? 'text-secondary' : 'text-on-surface'}`}
          >
            Vol. {volume.number}
          </span>
          {(range ?? ownTitle(volume.title, volume.number)) && (
            <span className="truncate font-mono text-label-sm text-outline">
              {range ?? ownTitle(volume.title, volume.number)}
            </span>
          )}
          <ReadMark read={read} />
        </span>
        <span className="inline-flex shrink-0 items-center gap-space-xs">
          {web ? (
            <span className="font-mono text-label-sm text-outline">
              {chapters.length} {chapters.length === 1 ? 'chapter' : 'chapters'}
            </span>
          ) : volume.status === 'preorder' ? (
            <span className="font-mono text-label-sm text-tertiary">Pre-order</span>
          ) : volume.readable ? (
            <Link to={`/read/prose/volume/${volume.id}`} className={READ_LINK}>
              <Icon name="book" className="h-3.5 w-3.5" />
              Read
            </Link>
          ) : (
            <NotHere />
          )}
        </span>
      </div>
      {expands && open && (
        <ul className="flex flex-col pb-space-sm pr-space-md">
          {chapters.map((chapter) => (
            <ChapterRow
              key={chapter.id}
              chapter={chapter}
              read={isChapterRead(chapter)}
              onBookmark={onBookmark}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

function Group({ title, children }: { title: string | null; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-space-xs">
      {title && (
        <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">{title}</h3>
      )}
      <ul className="flex flex-col rounded-xl bg-surface-container-low shadow-card">{children}</ul>
    </section>
  )
}

export function ProseContents({
  volumes,
  chapters,
  progress,
  volumeProgress,
  onBookmark,
}: {
  volumes: SeriesVolume[]
  chapters: SeriesChapter[]
  /** The furthest chapter any list records as read. */
  progress: number
  /** The furthest volume any list records as read. */
  volumeProgress: number
  onBookmark: (chapterId: number, bookmarked: boolean) => void
}) {
  if (volumes.length === 0 && chapters.length === 0) {
    return (
      <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
        Nothing in the library yet. Import files or map a source to fill it.
      </p>
    )
  }

  const isChapterRead = (chapter: SeriesChapter) => chapter.number <= progress
  const inRange = (volume: SeriesVolume, chapter: SeriesChapter) =>
    volume.first_part !== null &&
    volume.last_part !== null &&
    chapter.number >= volume.first_part &&
    chapter.number <= volume.last_part
  const chaptersOf = (volume: SeriesVolume) => chapters.filter((chapter) => inRange(volume, chapter))
  // Either edition's volume N read counts as volume N read: the import made
  // both editions share the light novel's numbering for exactly this.
  const isVolumeRead = (volume: SeriesVolume) => {
    if (volume.number <= volumeProgress) return true
    const own = chaptersOf(volume)
    return own.length > 0 && own.every(isChapterRead)
  }

  const light = volumes.filter((volume) => volume.edition === 'light')
  const web = volumes.filter((volume) => volume.edition === 'web')
  const loose = chapters.filter((chapter) => !volumes.some((volume) => inRange(volume, chapter)))
  // The web volume holding the next chapter to read starts open, so the place
  // to continue is on screen without a click.
  const nextChapter = chapters.find((chapter) => !isChapterRead(chapter))
  const both = light.length > 0 && web.length > 0

  const rows = (list: SeriesVolume[]) =>
    list.map((volume) => (
      <VolumeRow
        key={volume.id}
        volume={volume}
        chapters={chaptersOf(volume)}
        read={isVolumeRead(volume)}
        isChapterRead={isChapterRead}
        startOpen={nextChapter !== undefined && inRange(volume, nextChapter)}
        onBookmark={onBookmark}
      />
    ))

  return (
    <div className="flex flex-col gap-space-md">
      {light.length > 0 && <Group title={both ? 'Light novel' : null}>{rows(light)}</Group>}
      {web.length > 0 && <Group title={both ? 'Web novel' : null}>{rows(web)}</Group>}
      {loose.length > 0 && (
        <Group title={volumes.length > 0 ? 'Other chapters' : null}>
          {loose.map((chapter) => (
            <div
              key={chapter.id}
              className="border-b border-surface-container-highest/20 px-space-md last:border-0"
            >
              <ChapterRow chapter={chapter} read={isChapterRead(chapter)} onBookmark={onBookmark} />
            </div>
          ))}
        </Group>
      )}
    </div>
  )
}
