const KEY = 'search:recent'
const KEPT = 8

/**
 * The last few titles searched, newest first, in this browser only.
 *
 * Local rather than stored server-side: it is a shortcut back to a search,
 * not a record anyone else needs, and a list nobody can clear from another
 * device is not worth a table.
 */
export function recentSearches(): string[] {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((item) => typeof item === 'string') : []
  } catch {
    return []
  }
}

function write(list: string[]): string[] {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list))
  } catch {
    // A private window refuses storage; the search still runs.
  }
  return list
}

export function rememberSearch(query: string): string[] {
  const kept = recentSearches().filter((item) => item.toLowerCase() !== query.toLowerCase())
  return write([query, ...kept].slice(0, KEPT))
}

export function forgetSearches(): string[] {
  return write([])
}
