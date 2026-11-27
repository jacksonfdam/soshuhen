import type { Profile, Series } from '../../lib/api.ts'

/** Whose series this is, when it is not the manager's.

    The console lists every series on the server. One only someone else
    follows carries their faces, so the owner can tell it apart from their own;
    the manager's series, and imports no list holds, carry nothing. Without the
    profile list nothing is claimed rather than a guess drawn. */
export function holdersOf(
  series: Pick<Series, 'held_by'>,
  profiles: Profile[] | null,
): Profile[] | null {
  if (!profiles || series.held_by.length === 0) return null
  const manager = profiles.find((profile) => profile.is_manager)
  if (manager && series.held_by.includes(manager.id)) return null
  const holders = profiles.filter((profile) => series.held_by.includes(profile.id))
  return holders.length ? holders : null
}
