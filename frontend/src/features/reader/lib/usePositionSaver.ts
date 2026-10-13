import { useCallback, useEffect, useRef } from 'react'

import { api } from '../../../lib/api'

const DELAY_MS = 800

/**
 * Save where reading stands, once the page has stopped changing.
 *
 * An explicit call per page turn rather than an effect on the page number:
 * an effect would also run for the page restored on open, and with a
 * debounce it would save the placeholder page zero over the real position
 * before the restore landed.
 *
 * A failed save is not shown. The next page turn saves again, and an error
 * banner over the page being read costs more than one lost position.
 */
export function usePositionSaver(seriesId: number | null, chapterId: number | null) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current)
    },
    [chapterId],
  )

  return useCallback(
    (page: number, { immediately = false }: { immediately?: boolean } = {}) => {
      if (seriesId === null || chapterId === null) return
      if (timer.current !== null) clearTimeout(timer.current)
      const save = () => void api.saveReaderPosition(seriesId, chapterId, page).catch(() => undefined)
      if (immediately) save()
      else timer.current = setTimeout(save, DELAY_MS)
    },
    [seriesId, chapterId],
  )
}
