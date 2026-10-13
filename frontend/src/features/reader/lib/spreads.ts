import type { ReaderMode } from '../../../lib/api'

/** The pages shown together at each step of a paged mode. */
export function spreads(pageCount: number, mode: ReaderMode): number[][] {
  if (mode !== 'double') return Array.from({ length: pageCount }, (_, index) => [index])
  // The first page stands alone, the way a printed volume opens on its
  // cover; pairing it shifts every later spread by one and splits two-page
  // art down the middle.
  const groups: number[][] = pageCount > 0 ? [[0]] : []
  for (let index = 1; index < pageCount; index += 2) {
    groups.push(index + 1 < pageCount ? [index, index + 1] : [index])
  }
  return groups
}

export function spreadOf(groups: number[][], page: number): number {
  const found = groups.findIndex((group) => group.includes(page))
  return found === -1 ? 0 : found
}

export function clampPage(page: number, pageCount: number): number {
  if (!Number.isFinite(page) || pageCount === 0) return 0
  return Math.min(Math.max(Math.trunc(page), 0), pageCount - 1)
}
