import { avatarUrl } from '../lib/profiles'

// Spelled out rather than built from `size`: a class assembled by string
// interpolation is one the Tailwind scanner never sees, and it generates nothing.
const SIZE = {
  sm: 'h-avatar-sm w-avatar-sm',
  md: 'h-avatar-md w-avatar-md',
  lg: 'h-avatar-lg w-avatar-lg',
} as const

/** A profile's face. The art is original, one file per key, under public/avatars. */
export function Avatar({
  avatar,
  name,
  size = 'md',
}: {
  avatar: string
  name: string
  size?: keyof typeof SIZE
}) {
  return (
    <img
      src={avatarUrl(avatar)}
      alt={name}
      className={`${SIZE[size]} shrink-0 rounded-full object-cover`}
      draggable={false}
    />
  )
}
