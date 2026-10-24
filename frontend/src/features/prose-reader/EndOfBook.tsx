import { Link } from 'react-router-dom'

import type { ProseBookRef, ProseKind } from '../../lib/api'
import { Button, buttonClass } from '../../ui'

export function EndOfBook({
  kind,
  next,
  seriesId,
  state,
  onFinish,
  onNext,
}: {
  kind: ProseKind
  next: ProseBookRef | null
  seriesId: number
  state: 'idle' | 'busy' | 'done' | 'failed'
  onFinish: () => void
  onNext: () => void
}) {
  const noun = kind === 'volume' ? 'volume' : 'chapter'
  const nextLabel =
    next === null ? null : kind === 'volume' ? `Vol. ${next.number}` : `Ch ${next.number}`
  return (
    // The reader's own surface, not the page colour: this is the interface
    // speaking, not the book.
    <section className="mx-auto my-space-xl flex max-w-prose-column flex-col items-center gap-space-md rounded-xl bg-surface-container px-space-lg py-space-lg text-center font-sans text-on-surface">
      <h2 className="text-headline-sm">End of this {noun}</h2>
      <p className="text-body-md text-on-surface-variant">
        {state === 'done'
          ? 'Marked as read. Your lists will move forward shortly.'
          : state === 'failed'
            ? 'Could not mark it as read. Try again.'
            : `Marking it read moves your lists forward, never back.`}
      </p>
      <div className="flex flex-wrap justify-center gap-space-sm">
        {state !== 'done' && (
          <Button variant="surface" disabled={state === 'busy'} onClick={onFinish}>
            Mark as read
          </Button>
        )}
        {nextLabel && (
          <Button variant="primary" disabled={state === 'busy'} onClick={onNext}>
            Read {nextLabel}
          </Button>
        )}
        {!nextLabel && (
          <Link to={`/series/${seriesId}`} className={buttonClass({ variant: 'primary' })}>
            Back to the series
          </Link>
        )}
      </div>
    </section>
  )
}
