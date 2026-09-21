import { useEffect, useRef, useSyncExternalStore } from 'react'

export interface JobEvent {
  event: string
  job_id: number
  pct: number | null
  message: string
  /** Both are null on `job.progress` ticks and on a job the queue could not
      hand to a handler; only the outcome frames identify what finished. */
  job_type: string | null
  series_id: number | null
}

type Handler = (event: JobEvent) => void

/** What the interface can say about the stream. `reconnecting` is the one that
    matters: it is the difference between a quiet queue and a dead connection,
    which otherwise look identical on every screen. */
export type StreamStatus = 'connecting' | 'open' | 'reconnecting'

const EVENT_NAMES = ['job.progress', 'job.done', 'job.failed', 'job.retry']

// One stream for the whole application, not one per hook.
//
// Eight call sites use useJobEvents, and each used to open its own EventSource.
// Three are mounted at once on a series screen (the shell, the detail hook and
// the mapping panel), and an EventSource holds its connection open for as long
// as it lives. HTTP/1.1 allows six connections per origin *per browser*, shared
// across tabs, so two tabs of this app spent the entire budget on event streams
// and every later request queued behind them forever: the page rendered, and
// nothing in it ever loaded. It reads exactly like the interface freezing.
//
// The server already fans one Postgres LISTEN out to many subscribers. This is
// the same shape on the client: one connection, many handlers.
const handlers = new Set<Handler>()
const statusListeners = new Set<() => void>()
let source: EventSource | null = null
let status: StreamStatus = 'connecting'
let reopenTimer: ReturnType<typeof setTimeout> | null = null

function setStatus(next: StreamStatus): void {
  if (status === next) return
  status = next
  for (const listener of statusListeners) listener()
}

function forward(raw: MessageEvent): void {
  let payload: JobEvent
  try {
    payload = JSON.parse(raw.data)
  } catch {
    return // A malformed frame is not worth tearing the stream down for.
  }
  // A copy, so a handler that unsubscribes while this runs cannot mutate the
  // set being iterated.
  for (const handler of [...handlers]) handler(payload)
}

function open(): void {
  if (source !== null) return
  const stream = new EventSource('/api/events')
  source = stream
  stream.onopen = () => setStatus('open')
  stream.onerror = () => {
    // The browser retries on its own while the stream is CONNECTING. Once it
    // reaches CLOSED it has given up, and only reopening brings it back - which
    // is what a laptop waking from sleep leaves behind.
    setStatus('reconnecting')
    if (stream.readyState === EventSource.CLOSED) reopen()
  }
  for (const name of EVENT_NAMES) stream.addEventListener(name, forward as EventListener)
}

function close(): void {
  if (reopenTimer !== null) {
    clearTimeout(reopenTimer)
    reopenTimer = null
  }
  source?.close()
  source = null
  setStatus('connecting')
}

function reopen(): void {
  if (reopenTimer !== null) return
  reopenTimer = setTimeout(() => {
    reopenTimer = null
    if (handlers.size === 0) return
    source?.close()
    source = null
    open()
  }, 3000)
}

if (typeof document !== 'undefined') {
  // A tab that was backgrounded across a sleep comes back with a stream the
  // browser has already given up on. Nothing else would notice until the next
  // event that never arrives.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return
    if (handlers.size === 0) return
    if (source === null || source.readyState === EventSource.CLOSED) {
      source?.close()
      source = null
      open()
    }
  })
}

/**
 * Subscribe to the server-sent job stream. The stream is driven by Postgres
 * notifications, so a component that listens does not need to poll.
 *
 * Every caller shares one connection; the first subscriber opens it and the
 * last one to leave closes it.
 */
export function useJobEvents(onEvent: Handler): void {
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    const forwardToLatest: Handler = (event) => handler.current(event)
    handlers.add(forwardToLatest)
    open()
    return () => {
      handlers.delete(forwardToLatest)
      if (handlers.size === 0) close()
    }
  }, [])
}

/** The shared stream's state, for the one place in the interface that says so. */
export function useEventStreamStatus(): StreamStatus {
  return useSyncExternalStore(
    (listener) => {
      statusListeners.add(listener)
      return () => statusListeners.delete(listener)
    },
    () => status,
    () => 'connecting' as StreamStatus,
  )
}
