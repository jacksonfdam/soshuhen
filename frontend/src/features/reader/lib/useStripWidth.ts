import { useEffect, useRef, useState } from 'react'

import type { ReaderScale } from '../../../lib/api'

// Static, narrowest first, for the same reason as the maps in styles.ts.
export const STRIP_WIDTHS = [
  'w-full max-w-xl',
  'w-full max-w-2xl',
  'w-full max-w-3xl',
  'w-full max-w-4xl',
  'w-full max-w-5xl',
  'w-full max-w-6xl',
  'w-full max-w-7xl',
  'w-full',
] as const

const KEY = 'reader:strip-width'

// One notch of a mouse wheel. A trackpad pinch arrives as a stream of small
// deltas, and without a threshold it swept the whole range in one gesture.
const NOTCH = 100

function stored(): number | null {
  try {
    const value = window.localStorage.getItem(KEY)
    if (value === null) return null
    const step = Number(value)
    return Number.isInteger(step) && step >= 0 && step < STRIP_WIDTHS.length ? step : null
  } catch {
    return null
  }
}

function store(step: number | null): void {
  try {
    if (step === null) window.localStorage.removeItem(KEY)
    else window.localStorage.setItem(KEY, String(step))
  } catch {
    // A private window refuses storage; the width then lasts as long as the page.
  }
}

/**
 * The strip's column width, set with Ctrl and the wheel and reset with Ctrl+0.
 *
 * Kept in this browser rather than in the series prefs: the right width is a
 * property of the screen, and a phone and a desktop reading the same series
 * want different ones. Null follows the scale.
 */
export function useStripWidth(enabled: boolean, scale: ReaderScale): string | null {
  const [step, setStep] = useState<number | null>(stored)
  const current = useRef(step)
  current.current = step
  const fallback = useRef(scale)
  fallback.current = scale

  useEffect(() => {
    if (!enabled) return
    let travelled = 0

    function change(next: number | null) {
      // Ahead of the render: a fast wheel delivers several notches before
      // React gets to one, and each must step from the last, not the first.
      current.current = next
      setStep(next)
      store(next)
    }

    function onWheel(event: WheelEvent) {
      if (!event.ctrlKey) return
      // Without this the browser zooms the whole page instead.
      event.preventDefault()
      travelled += event.deltaY
      if (Math.abs(travelled) < NOTCH) return
      const wider = travelled < 0
      travelled = 0
      const from =
        current.current ?? (fallback.current === 'fit_width' ? STRIP_WIDTHS.length - 1 : 2)
      const to = Math.min(Math.max(from + (wider ? 1 : -1), 0), STRIP_WIDTHS.length - 1)
      if (to !== current.current) change(to)
    }

    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key === '0' && current.current !== null) {
        event.preventDefault()
        change(null)
      }
    }

    window.addEventListener('wheel', onWheel, { passive: false })
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('wheel', onWheel)
      window.removeEventListener('keydown', onKey)
    }
  }, [enabled])

  return enabled && step !== null ? STRIP_WIDTHS[step] : null
}
