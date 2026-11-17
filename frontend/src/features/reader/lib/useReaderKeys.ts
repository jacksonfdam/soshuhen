import { useEffect, useRef } from 'react'

import { keptByControl } from './readerKeyOwner'

export interface ReaderKeyActions {
  left: () => void
  right: () => void
  forward: () => void
  back: () => void
  previousChapter: () => void
  nextChapter: () => void
  fullscreen: () => void
  narrate: () => void
  escape: () => void
}

export function useReaderKeys(actions: ReaderKeyActions): void {
  // A ref, so the listener is bound once and still calls the latest closures.
  const latest = useRef(actions)
  latest.current = actions

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (
        target instanceof HTMLElement &&
        keptByControl(target.tagName, target.getAttribute('type'), event.key)
      ) {
        return
      }
      const run = latest.current
      switch (event.key) {
        case 'ArrowLeft':
          run.left()
          break
        case 'ArrowRight':
          run.right()
          break
        case ' ':
          if (event.shiftKey) run.back()
          else run.forward()
          break
        case '[':
          run.previousChapter()
          break
        case ']':
          run.nextChapter()
          break
        case 'f':
          run.fullscreen()
          break
        case 'n':
          run.narrate()
          break
        case 'Escape':
          run.escape()
          break
        default:
          return
      }
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
