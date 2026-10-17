/**
 * The browser's own Notification API, and nothing else: no push service, no
 * service worker. That is what keeps notifications free of anything outside
 * this installation, and it is also why one is raised only while a tab is open.
 */

const ENABLED_KEY = 'soshuhen.desktopNotifications'

// Android Chrome exposes Notification and grants the permission, then throws
// on the constructor: it raises notifications only through a service worker.
// Once that has happened the browser is treated as unsupported, so the panel
// stops offering a switch that can never fire.
let constructorRefused = false

/** The API exists only in a secure context: HTTPS, or localhost. */
export function supported(): boolean {
  return (
    !constructorRefused &&
    typeof window !== 'undefined' &&
    'Notification' in window &&
    window.isSecureContext
  )
}

export function permission(): NotificationPermission | 'unsupported' {
  return supported() ? Notification.permission : 'unsupported'
}

/** Call only from a click: browsers ignore, or remember against the site, a
    permission request made without one. */
export function request(): Promise<NotificationPermission> {
  return Notification.requestPermission()
}

/** A per-browser mute that leaves the system permission alone, so turning
    notifications back on does not mean digging through site settings. */
export function enabled(): boolean {
  try {
    return window.localStorage.getItem(ENABLED_KEY) !== 'off'
  } catch {
    return true // Storage blocked (a private window): fall back to the default.
  }
}

export function setEnabled(on: boolean): void {
  try {
    window.localStorage.setItem(ENABLED_KEY, on ? 'on' : 'off')
  } catch {
    // Nowhere to remember it; the switch resets with the page.
  }
}

export function show(opts: {
  id: number
  title: string
  body: string
  icon?: string
  onClick: () => void
}): void {
  if (permission() !== 'granted' || !enabled()) return
  let notification: Notification
  try {
    notification = new Notification(opts.title, {
      body: opts.body,
      icon: opts.icon,
      // One tag per row: two open tabs hearing the same event replace each
      // other's notification instead of stacking a duplicate.
      tag: `soshuhen-${opts.id}`,
    })
  } catch {
    constructorRefused = true
    return
  }
  notification.onclick = () => {
    window.focus()
    opts.onClick()
    notification.close()
  }
}
