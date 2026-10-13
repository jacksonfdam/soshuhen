import { Link } from 'react-router-dom'

import type { ReaderChapterRef } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { Button, buttonClass } from '../../ui'

export function EndOfChapter({
  current,
  next,
  seriesId,
  onNext,
}: {
  current: ReaderChapterRef
  next: ReaderChapterRef | null
  seriesId: number
  onNext: () => void
}) {
  return (
    <section className="flex min-h-[60vh] w-full flex-col items-center justify-center gap-space-md px-space-lg text-center">
      <p className="font-mono text-label-md text-on-surface-variant">
        End of Ch. {formatChapter(current.number)}
      </p>
      {next ? (
        <Button
          variant="primary"
          icon="chevron_right"
          onClick={(event) => {
            event.stopPropagation()
            onNext()
          }}
        >
          Ch. {formatChapter(next.number)}
          {next.title ? ` · ${next.title}` : ''}
        </Button>
      ) : (
        <>
          <p className="text-body-md text-on-surface">You are caught up.</p>
          <Link to={`/series/${seriesId}`} className={buttonClass({ variant: 'surface' })}>
            Back to the series
          </Link>
        </>
      )}
    </section>
  )
}
