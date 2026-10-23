import { useEffect, useRef, type ReactNode } from 'react'

import type { ReaderScale } from '../../lib/api'
import { STRIP_FIT } from './lib/styles'
import { PageImage } from './PageImage'

export function StripView({
  chapterId,
  pageCount,
  scale,
  width,
  initialPage,
  onPage,
  onEnd,
  onTap,
  end,
}: {
  chapterId: number
  pageCount: number
  scale: ReaderScale
  width: string | null
  initialPage: number
  onPage: (page: number) => void
  onEnd: () => void
  onTap: () => void
  end: ReactNode
}) {
  const pages = useRef<(HTMLDivElement | null)[]>([])
  const endRef = useRef<HTMLDivElement | null>(null)
  const callbacks = useRef({ onPage, onEnd })
  callbacks.current = { onPage, onEnd }
  const start = useRef(initialPage)
  start.current = initialPage

  // Once per chapter. Rerunning on every page change would yank the strip back
  // to wherever the last saved page was.
  useEffect(() => {
    pages.current[start.current]?.scrollIntoView()
  }, [chapterId])

  useEffect(() => {
    const ratios = new Map<number, number>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          ratios.set(Number((entry.target as HTMLElement).dataset.index), entry.intersectionRatio)
        }
        let best = -1
        let highest = 0
        for (const [index, ratio] of ratios) {
          if (ratio > highest) {
            best = index
            highest = ratio
          }
        }
        if (best >= 0) callbacks.current.onPage(best)
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1] },
    )
    for (const element of pages.current) if (element) observer.observe(element)

    const ending = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) callbacks.current.onEnd()
    })
    if (endRef.current) ending.observe(endRef.current)

    return () => {
      observer.disconnect()
      ending.disconnect()
    }
  }, [chapterId, pageCount])

  return (
    <div onClick={onTap} className="mx-auto flex w-full flex-col items-center">
      {Array.from({ length: pageCount }, (_, index) => (
        <div
          key={index}
          data-index={index}
          ref={(element) => {
            pages.current[index] = element
          }}
          // A height before the image loads, so the observer and the restore
          // scroll have something to measure.
          className="flex min-h-[50vh] w-full justify-center"
        >
          <PageImage
            chapterId={chapterId}
            index={index}
            eager={Math.abs(index - initialPage) < 3}
            className={width ?? STRIP_FIT[scale]}
          />
        </div>
      ))}
      <div ref={endRef} className="w-full">
        {end}
      </div>
    </div>
  )
}
