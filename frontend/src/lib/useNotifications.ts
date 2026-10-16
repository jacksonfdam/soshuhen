import { useCallback, useEffect, useRef } from 'react'

import { api, type AppNotification, type NotificationPage } from './api'
import { show } from './desktopNotifications'
import { formatChapter } from './format'
import { useAsyncData, type AsyncData } from './useAsyncData'
import { useEventStreamStatus, useJobEvents } from './useEvents'

function range(first: number, last: number): string {
  return first === last ? formatChapter(first) : `${formatChapter(first)}–${formatChapter(last)}`
}

/** One line saying what a notification found. */
export function summary(n: AppNotification): string {
  const span = range(n.first_number, n.last_number)
  switch (n.kind) {
    case 'chapters':
      return `${n.count} new ${n.count === 1 ? 'chapter' : 'chapters'} (${span})`
    case 'volumes':
      return `${n.count === 1 ? 'Volume' : 'Volumes'} ${span} available`
    case 'parts':
      return `Volume ${formatChapter(n.volume_number ?? 0)}: ${n.count === 1 ? 'part' : 'parts'} ${span}`
  }
}

function markedRead(page: NotificationPage, ids: Set<number> | 'all'): NotificationPage {
  const now = new Date().toISOString()
  const items = page.items.map((item) =>
    item.read_at === null && (ids === 'all' || ids.has(item.id)) ? { ...item, read_at: now } : item,
  )
  const newlyRead = items.filter((item, index) => item.read_at !== page.items[index].read_at).length
  return {
    items,
    // Unread rows beyond the page are still unread; only what was marked here
    // comes off the count.
    unread_count: ids === 'all' ? 0 : Math.max(0, page.unread_count - newlyRead),
  }
}

/**
 * The bell's data. New rows arrive over the shared event stream, never by
 * polling; a tab that is not in front also raises a desktop notification,
 * since a user looking at the page has the badge already.
 */
export function useNotifications(onOpen: (n: AppNotification) => void): {
  page: AsyncData<NotificationPage>
  markRead: (id: number) => void
  markAllRead: () => void
} {
  const page = useAsyncData(api.notifications)
  const { reload, setData } = page
  const open = useRef(onOpen)
  open.current = onOpen

  useJobEvents((event) => {
    if (event.event !== 'notification.new') return
    if (document.visibilityState === 'visible') {
      reload()
      return
    }
    // One request serves both the list and the popup's content.
    api
      .notifications()
      .then((fresh) => {
        setData(fresh)
        const found = fresh.items.find((item) => item.id === event.notification_id)
        if (!found) return
        show({
          id: found.id,
          title: found.series_title,
          body: summary(found),
          icon: found.cover_url ?? undefined,
          onClick: () => open.current(found),
        })
      })
      .catch(reload)
  })

  // Whatever arrived while the stream was down is caught up in the list. It is
  // not raised on the desktop after the fact.
  const status = useEventStreamStatus()
  const previous = useRef(status)
  useEffect(() => {
    if (previous.current === 'reconnecting' && status === 'open') reload()
    previous.current = status
  }, [status, reload])

  const markRead = useCallback(
    (id: number) => {
      setData((current) => (current ? markedRead(current, new Set([id])) : current))
      api.markNotificationRead(id).catch(reload)
    },
    [setData, reload],
  )

  const markAllRead = useCallback(() => {
    setData((current) => (current ? markedRead(current, 'all') : current))
    api.markAllNotificationsRead().catch(reload)
  }, [setData, reload])

  return { page, markRead, markAllRead }
}
