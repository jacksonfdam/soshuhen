import type { Profile, ProfilePatch } from './api.ts'

/** Keys the server accepts; the art is `public/avatars/<key>.svg`. */
export const AVATAR_KEYS: readonly string[] = Array.from(
  { length: 12 },
  (_, index) => `avatar-${String(index + 1).padStart(2, '0')}`,
)

export function avatarUrl(key: string): string {
  // A key the art no longer has still draws a face rather than a broken image.
  return `/avatars/${AVATAR_KEYS.includes(key) ? key : AVATAR_KEYS[0]}.svg`
}

export function validPin(pin: string): boolean {
  return /^\d{4,6}$/.test(pin)
}

export function validName(name: string): boolean {
  const trimmed = name.trim()
  return trimmed.length >= 1 && trimmed.length <= 40
}

export interface ProfileDraft {
  name: string
  avatar: string
  /** Typed into the PIN field. Empty means leave the PIN as it is. */
  pin: string
  clearPin: boolean
}

/** Only what changed, or null when nothing did.

    An empty PIN field keeps the stored PIN: the field cannot show the PIN it
    is guarding, so empty is what every edit of a name or avatar looks like.
    Clearing it has to be its own, explicit choice. */
export function profilePatch(before: Profile, draft: ProfileDraft): ProfilePatch | null {
  const patch: ProfilePatch = {}
  const name = draft.name.trim()
  if (name !== before.name) patch.name = name
  if (draft.avatar !== before.avatar) patch.avatar = draft.avatar
  if (draft.clearPin) patch.pin = null
  else if (draft.pin) patch.pin = draft.pin
  return Object.keys(patch).length ? patch : null
}

/** The position changes that move one profile a step, or none at either end. */
export function reorder(
  profiles: Profile[],
  id: number,
  direction: -1 | 1,
): { id: number; position: number }[] {
  const sorted = [...profiles].sort((a, b) => a.position - b.position || a.id - b.id)
  const at = sorted.findIndex((profile) => profile.id === id)
  if (at < 0 || sorted[at + direction] === undefined) return []
  ;[sorted[at], sorted[at + direction]] = [sorted[at + direction], sorted[at]]
  // Everyone is renumbered to their index, not only the two that swapped:
  // deleting profiles leaves gaps in the stored positions, and writing indices
  // to two of them alone sorted the others out of order.
  return sorted
    .map((profile, index) => ({ id: profile.id, position: index, before: profile.position }))
    .filter((change) => change.position !== change.before)
    .map(({ id: changed, position }) => ({ id: changed, position }))
}

/** Headers for a request made on another profile's behalf. The console acts
    as the manager by sending none; naming a profile is the exception. */
export function profileHeaders(profileId?: number): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (profileId !== undefined) headers['X-Soshuhen-Profile'] = String(profileId)
  return headers
}
