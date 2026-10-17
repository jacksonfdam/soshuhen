/**
 * Whether another tab of this app is in front, asked at the moment it matters.
 *
 * Visibility is per tab, so a tab in the background cannot tell on its own
 * that the user is looking at the app in another one. Nothing is remembered
 * between questions: a tab that closed while in front would otherwise leave a
 * stale answer behind it.
 */

const CHANNEL = 'soshuhen-presence'
const ASK = 'anyone-visible'
const ANSWER = 'visible'

const channel =
  typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(CHANNEL)

channel?.addEventListener('message', (event: MessageEvent) => {
  if (event.data === ASK && document.visibilityState === 'visible') channel.postMessage(ANSWER)
})

/** A sender never hears its own message, so this tab's own visibility is not counted. */
export function anotherTabVisible(waitMs = 150): Promise<boolean> {
  if (channel === null) return Promise.resolve(false)
  return new Promise((resolve) => {
    const onMessage = (event: MessageEvent) => {
      if (event.data !== ANSWER) return
      finish(true)
    }
    const timer = setTimeout(() => finish(false), waitMs)
    function finish(answer: boolean) {
      clearTimeout(timer)
      channel?.removeEventListener('message', onMessage)
      resolve(answer)
    }
    channel.addEventListener('message', onMessage)
    channel.postMessage(ASK)
  })
}
