import { useState } from 'react'

import { readerPageUrl } from '../../lib/api'
import { Button } from '../../ui'

/**
 * One page, or a page-sized placeholder that says it could not load.
 *
 * A failed page must not take the chapter down with it: the source may have
 * dropped one request, and the page after it is very likely fine.
 */
export function PageImage({
  chapterId,
  index,
  className,
  eager = false,
}: {
  chapterId: number
  index: number
  className: string
  eager?: boolean
}) {
  const [attempt, setAttempt] = useState(0)
  const [failed, setFailed] = useState(false)

  if (failed) {
    return (
      <div className="flex aspect-[2/3] w-full max-w-xl flex-col items-center justify-center gap-space-md bg-surface-container text-on-surface-variant">
        <p className="text-body-md">Page {index + 1} could not be loaded.</p>
        <Button
          onClick={(event) => {
            event.stopPropagation()
            setFailed(false)
            setAttempt((value) => value + 1)
          }}
        >
          Try again
        </Button>
      </div>
    )
  }

  // The attempt in the query string is what makes a retry a new request: the
  // browser would otherwise answer from its memory of the failure.
  const url = readerPageUrl(chapterId, index)
  const src = attempt === 0 ? url : `${url}?attempt=${attempt}`
  return (
    <img
      src={src}
      alt={`Page ${index + 1}`}
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      draggable={false}
      onError={() => setFailed(true)}
      className={`select-none ${className}`}
    />
  )
}
