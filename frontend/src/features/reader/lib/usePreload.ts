import { useEffect } from 'react'

/**
 * Ask the browser for these images before they are on screen.
 *
 * The images are never cancelled on cleanup. A page turn would cancel the
 * request for the page after next, which the next turn asks for again, and
 * for a streamed chapter the server is fetching it from the source either way.
 */
export function usePreload(urls: string[]): void {
  const key = urls.join('|')
  useEffect(() => {
    for (const url of key ? key.split('|') : []) {
      const image = new Image()
      image.decoding = 'async'
      image.src = url
    }
  }, [key])
}
