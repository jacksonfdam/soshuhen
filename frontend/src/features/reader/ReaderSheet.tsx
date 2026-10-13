import type { ReactNode } from 'react'

import { Icon } from '../../ui'
import { useScrollLock } from '../../ui/useScrollLock'

/** A bottom sheet below xl, where a thumb reaches it; a centred panel above. */
export function ReaderSheet({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useScrollLock(true)
  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-surface-container-lowest/70 xl:items-center"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-[85vh] w-full flex-col overflow-hidden rounded-t-xl bg-surface-container shadow-overlay xl:max-w-lg xl:rounded-xl"
      >
        <div className="flex items-center justify-between px-space-lg py-space-md">
          <h2 className="text-headline-sm text-on-surface">{title}</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-lg p-space-xs text-outline hover:bg-surface-container-high hover:text-on-surface"
          >
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>
        <div className="overflow-y-auto px-space-lg pb-space-lg">{children}</div>
      </div>
    </div>
  )
}
