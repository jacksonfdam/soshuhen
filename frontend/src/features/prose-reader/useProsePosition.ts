import { useCallback, useEffect, useRef, useState } from 'react'

import { api, type ProseKind } from '../../lib/api'

const SAVE_AFTER_MS = 1500

/** The line on screen a place is measured from: a third of the way down,
    roughly where the eye is while reading, rather than the very top edge. */
function anchor(): number {
  return window.innerHeight / 3
}

/** The section the reading line sits in, and how far through it. */
function measure(column: HTMLElement): { section: number; fraction: number } | null {
  const sections = column.querySelectorAll<HTMLElement>('[data-section]')
  if (sections.length === 0) return null
  const line = anchor()
  let found = sections[0]
  for (const element of sections) {
    if (element.getBoundingClientRect().top <= line) found = element
    else break
  }
  const box = found.getBoundingClientRect()
  const fraction = box.height > 0 ? Math.min(1, Math.max(0, (line - box.top) / box.height)) : 0
  return { section: Number(found.dataset.section), fraction }
}

/** Scroll so the reading line lands where a saved place says. */
export function scrollToPlace(column: HTMLElement, section: number, fraction: number) {
  const element = column.querySelector<HTMLElement>(`[data-section="${section}"]`)
  if (!element) return
  const box = element.getBoundingClientRect()
  window.scrollTo({ top: window.scrollY + box.top + box.height * fraction - anchor() })
}

/**
 * Where reading stands, saved as the reader scrolls.
 *
 * Debounced, so a long scroll is one write, and flushed when the page goes
 * away, so closing the tab mid-chapter does not lose the last minute. Nothing
 * is tracked until `ready`: before the place is restored, the page sits at the
 * top, and saving that would overwrite the place it is about to scroll to.
 */
export function useProsePosition(
  seriesId: number | null,
  kind: ProseKind,
  id: number,
  column: HTMLElement | null,
  ready: boolean,
) {
  const [current, setCurrent] = useState({ section: 0, fraction: 0 })
  const pending = useRef<{ section: number; fraction: number } | null>(null)
  const timer = useRef<number | null>(null)

  const flush = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
    const place = pending.current
    pending.current = null
    if (place === null || seriesId === null) return
    // A failed save is not worth an interruption: the next scroll saves again.
    void api.saveProsePosition(seriesId, { kind, id }, place.section, place.fraction).catch(() => {})
  }, [seriesId, kind, id])

  useEffect(() => {
    if (!ready || column === null) return
    let frame = 0
    const onScroll = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const place = measure(column)
        if (place === null) return
        setCurrent(place)
        pending.current = place
        if (timer.current !== null) window.clearTimeout(timer.current)
        timer.current = window.setTimeout(flush, SAVE_AFTER_MS)
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('pagehide', flush)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('pagehide', flush)
      flush()
    }
  }, [ready, column, flush])

  return current
}
