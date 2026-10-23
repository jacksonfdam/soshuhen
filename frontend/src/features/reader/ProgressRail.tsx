/**
 * How far down the strip the reader is, always on screen.
 *
 * The page slider is the strip's only other gauge, and it stays out of a
 * strip on a desktop so it does not sit over the panels being read. A rail
 * along the top edge covers nothing.
 */
export function ProgressRail({ page, pageCount }: { page: number; pageCount: number }) {
  const done = pageCount > 0 ? (page + 1) / pageCount : 0
  return (
    <div
      role="progressbar"
      aria-label="Chapter progress"
      aria-valuemin={1}
      aria-valuemax={pageCount}
      aria-valuenow={page + 1}
      className="pointer-events-none fixed inset-x-0 top-0 z-40 h-1 bg-surface-container/60"
    >
      <div
        className="h-full origin-left bg-primary transition-transform"
        style={{ transform: `scaleX(${done})` }}
      />
    </div>
  )
}
