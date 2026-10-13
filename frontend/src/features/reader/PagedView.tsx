import type { MouseEvent } from 'react'

import type { ReaderScale } from '../../lib/api'
import { PAGED_FIT } from './lib/styles'
import { PageImage } from './PageImage'

export type Zone = 'left' | 'center' | 'right'

export function PagedView({
  chapterId,
  group,
  scale,
  rtl,
  onZone,
}: {
  chapterId: number
  group: number[]
  scale: ReaderScale
  rtl: boolean
  onZone: (zone: Zone) => void
}) {
  // A right-to-left spread puts the earlier page on the right.
  const ordered = rtl ? [...group].reverse() : group

  function click(event: MouseEvent<HTMLDivElement>) {
    const { left, width } = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - left) / width
    onZone(x < 1 / 3 ? 'left' : x > 2 / 3 ? 'right' : 'center')
  }

  return (
    <div onClick={click} className="flex min-h-screen w-full cursor-pointer items-center justify-center">
      {ordered.map((index) => (
        <PageImage
          key={index}
          chapterId={chapterId}
          index={index}
          eager
          className={group.length > 1 ? 'max-h-screen w-1/2 object-contain' : PAGED_FIT[scale]}
        />
      ))}
    </div>
  )
}
