import type { Series } from '../../lib/api.ts'

/** What removing a selection will do, for the confirm dialog.

    The console lists every series on the server, so one selection can mix
    series only you follow (removed, their queue cancelled with them), series
    someone else also follows (leave your library only) and series only someone
    else follows (left alone). One fixed list of consequences promised all of
    them the first. */
export function removeConsequences(
  selected: Pick<Series, 'held_by'>[],
  managerId: number | null,
): string[] {
  const mine = (series: Pick<Series, 'held_by'>) =>
    managerId !== null && series.held_by.includes(managerId)
  // Without the profile list nothing is known about who follows what, and
  // claiming a series is someone else's would be a guess.
  const othersOnly =
    managerId === null ? 0 : selected.filter((s) => s.held_by.length > 0 && !mine(s)).length
  const shared = selected.filter((s) => mine(s) && s.held_by.length > 1).length
  const removedOutright = selected.length - othersOnly - shared

  const lines: string[] = []
  if (removedOutright > 0) lines.push('Anything queued for them is cancelled.')
  if (shared > 0) {
    lines.push(
      `${shared} series someone else also follows ${shared === 1 ? 'leaves' : 'leave'} your library only; ${shared === 1 ? 'it stays' : 'they stay'} on the server for them.`,
    )
  }
  if (othersOnly > 0) {
    lines.push(
      `${othersOnly} series ${othersOnly === 1 ? 'is' : 'are'} only on someone else's lists and will be left alone.`,
    )
  }
  lines.push(
    'Chapters already downloaded stay on disk and in Komga.',
    'A list sync will not bring them back to your library.',
    'Your MyAnimeList and AniList entries are left as they are.',
  )
  return lines
}
