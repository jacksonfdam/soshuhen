export function PageSlider({
  page,
  pageCount,
  rtl,
  onSeek,
}: {
  page: number
  pageCount: number
  rtl: boolean
  onSeek: (page: number) => void
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-space-sm rounded-full bg-surface-container-highest px-space-md py-space-xs">
      <span className="w-8 text-right font-mono text-label-sm text-on-surface">{page + 1}</span>
      <input
        type="range"
        min={0}
        max={Math.max(pageCount - 1, 0)}
        value={page}
        // The slider runs the way the pages do, so dragging toward the end of
        // a right-to-left chapter means dragging left.
        dir={rtl ? 'rtl' : 'ltr'}
        aria-label="Page"
        onChange={(event) => onSeek(Number(event.target.value))}
        className="min-w-0 flex-1 accent-primary"
      />
      <span className="w-8 font-mono text-label-sm text-on-surface-variant">{pageCount}</span>
    </div>
  )
}
