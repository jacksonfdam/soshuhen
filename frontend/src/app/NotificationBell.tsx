import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import type { AppNotification } from '../lib/api'
import * as desktop from '../lib/desktopNotifications'
import { relativeTime } from '../lib/format'
import { summary, useNotifications } from '../lib/useNotifications'
import { Badge, EmptyState, Icon, IconButton, Toggle } from '../ui'

/**
 * The header's bell. It lives with the shell rather than in a feature folder:
 * every screen shows it, and no screen owns it.
 */
export function NotificationBell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const panel = useRef<HTMLDivElement>(null)

  const openSeries = useCallback(
    (n: AppNotification, markRead: (id: number) => void) => {
      if (n.read_at === null) markRead(n.id)
      navigate(`/series/${n.series_id}`)
    },
    [navigate],
  )

  // The desktop notification's click lands here, possibly long after the
  // render that raised it, so it reaches markRead through a ref.
  const markReadRef = useRef<(id: number) => void>(() => {})
  const { page, markRead, markAllRead } = useNotifications((n) =>
    openSeries(n, markReadRef.current),
  )
  markReadRef.current = markRead

  useEffect(() => setOpen(false), [location.pathname])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onPointer = (event: MouseEvent) => {
      if (panel.current && !panel.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [open])

  const unread = page.data?.unread_count ?? 0

  return (
    <div ref={panel} className="relative shrink-0">
      <IconButton
        icon="bell"
        label="Notifications"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((current) => !current)}
      />
      {unread > 0 && (
        <span className="pointer-events-none absolute -right-2 -top-2">
          <Badge tone="error">{unread}</Badge>
        </span>
      )}
      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          // Below sm the panel spans the screen under the header; a 24rem card
          // hung off the bell would run off the left edge of a phone.
          className="fixed inset-x-gutter top-20 z-50 flex flex-col overflow-hidden rounded-xl bg-surface-container shadow-overlay sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-space-sm sm:w-96"
        >
          <div className="flex items-center justify-between gap-space-sm border-b border-white/5 px-space-md py-space-sm">
            <h2 className="text-title-md text-on-surface">Notifications</h2>
            <button
              type="button"
              disabled={unread === 0}
              onClick={markAllRead}
              className="text-label-md text-primary hover:underline disabled:cursor-not-allowed disabled:text-outline disabled:no-underline"
            >
              Mark all as read
            </button>
          </div>
          <Items
            data={page.data?.items ?? null}
            error={page.error}
            onSelect={(n) => openSeries(n, markRead)}
          />
          <PermissionFooter />
        </div>
      )}
    </div>
  )
}

function Items({
  data,
  error,
  onSelect,
}: {
  data: AppNotification[] | null
  error: string | null
  onSelect: (n: AppNotification) => void
}) {
  if (data === null) {
    return (
      <p className="px-space-md py-space-md text-body-sm text-on-surface-variant">
        {error ?? 'Loading…'}
      </p>
    )
  }
  if (data.length === 0) {
    return (
      <div className="p-space-sm">
        <EmptyState
          icon="bell"
          title="No notifications yet"
          detail="New chapters found at a source show up here."
        />
      </div>
    )
  }
  return (
    <ul className="max-h-96 overflow-y-auto">
      {data.map((n) => (
        <li key={n.id}>
          <button
            type="button"
            onClick={() => onSelect(n)}
            className={`flex w-full items-center gap-space-sm px-space-md py-space-sm text-left transition-colors hover:bg-surface-container-high ${
              n.read_at === null ? 'bg-primary/10' : ''
            }`}
          >
            <span className="flex h-12 w-9 shrink-0 items-center justify-center overflow-hidden rounded bg-surface-container-high text-on-surface-variant">
              {n.cover_url ? (
                <img src={n.cover_url} alt="" className="h-full w-full object-cover" />
              ) : (
                <Icon name="book" />
              )}
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-body-md text-on-surface">{n.series_title}</span>
              <span className="text-body-sm text-on-surface-variant">{summary(n)}</span>
              <span className="font-mono text-label-sm text-outline">{relativeTime(n.created_at)}</span>
            </span>
            {n.read_at === null && (
              <span className="h-2 w-2 shrink-0 rounded-full bg-primary">
                <span className="sr-only">Unread</span>
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  )
}

function PermissionFooter() {
  const [permission, setPermission] = useState(desktop.permission)
  const [enabled, setEnabled] = useState(desktop.enabled)

  if (permission === 'unsupported') return null
  return (
    <div className="border-t border-white/5 px-space-md py-space-sm">
      {permission === 'default' && (
        <button
          type="button"
          onClick={() => desktop.request().then(setPermission)}
          className="text-label-md text-primary hover:underline"
        >
          Enable desktop notifications
        </button>
      )}
      {permission === 'granted' && (
        <Toggle
          label="Desktop notifications"
          checked={enabled}
          onChange={(on) => {
            desktop.setEnabled(on)
            setEnabled(on)
          }}
        />
      )}
      {permission === 'denied' && (
        <p className="text-body-sm text-on-surface-variant">Blocked in your browser's site settings</p>
      )}
    </div>
  )
}
