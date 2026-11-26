import type { RemovalResult } from '../../lib/api.ts'

/** What a removal did, said plainly.

    The console sees every series, so a selection can hold series someone else
    still follows (they leave this library only) and series only someone else
    follows (left alone). "Removed 0" for either reads as a broken button. */
export function removalNotice(result: Pick<RemovalResult, 'removed' | 'deleted' | 'skipped'>): string {
  const skipped = result.skipped.length
  if (result.removed === 0) {
    if (skipped === 0) return 'Nothing removed.'
    return `Nothing removed: ${skipped} series ${skipped === 1 ? 'is' : 'are'} only on someone else's lists. Remove ${skipped === 1 ? 'it' : 'them'} from their profile instead.`
  }
  const removed = `Removed ${result.removed} series from your library.`
  const after =
    result.deleted > 0
      ? 'A list sync will not bring them back.'
      : `Someone else still follows ${result.removed === 1 ? 'it' : 'them'}, so ${result.removed === 1 ? 'it stays' : 'they stay'} on the server for them.`
  const left = skipped
    ? ` ${skipped} more ${skipped === 1 ? 'is' : 'are'} only on someone else's lists and ${skipped === 1 ? 'was' : 'were'} left alone.`
    : ''
  return `${removed} ${after}${left}`
}
