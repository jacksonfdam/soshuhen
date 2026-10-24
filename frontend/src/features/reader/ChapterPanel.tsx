import { useCallback } from 'react'

import { api } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { Button } from '../../ui'
import { ReaderSheet } from '../../ui/ReaderSheet'

export function ChapterPanel({
  seriesId,
  currentId,
  onOpen,
  onClose,
}: {
  seriesId: number
  currentId: number
  onOpen: (chapterId: number) => void
  onClose: () => void
}) {
  const load = useCallback(() => api.readerChapters(seriesId), [seriesId])
  const { data, error, reload } = useAsyncData(load)

  return (
    <ReaderSheet title="Chapters" onClose={onClose}>
      {!data && !error && <p className="text-body-md text-on-surface-variant">Loading…</p>}
      {!data && error && (
        <div className="flex flex-col items-start gap-space-sm">
          <p className="text-body-md text-error">{error}</p>
          <Button size="sm" onClick={reload}>
            Try again
          </Button>
        </div>
      )}
      {data && (
        <ul className="flex flex-col">
          {[...data].reverse().map((chapter) => {
            const current = chapter.id === currentId
            return (
              <li key={chapter.id}>
                <button
                  type="button"
                  aria-current={current ? 'true' : undefined}
                  onClick={() => onOpen(chapter.id)}
                  className={`flex w-full items-center gap-space-sm rounded-lg px-space-sm py-space-sm text-left transition-colors ${
                    current
                      ? 'bg-primary/[0.12] text-primary'
                      : 'text-on-surface hover:bg-surface-container-high'
                  }`}
                >
                  <span className="font-mono text-label-md">Ch. {formatChapter(chapter.number)}</span>
                  {chapter.title && (
                    <span className="min-w-0 flex-1 truncate text-body-sm text-on-surface-variant">
                      {chapter.title}
                    </span>
                  )}
                  {/* Not a failure: a chapter that is not downloaded is read
                      from its source and saved as it is read. */}
                  {chapter.state !== 'downloaded' && (
                    <span className="ml-auto shrink-0 font-mono text-label-sm text-outline">
                      streams
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </ReaderSheet>
  )
}
