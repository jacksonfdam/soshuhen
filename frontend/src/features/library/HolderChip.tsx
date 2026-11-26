import type { Profile } from '../../lib/api'
import { Avatar } from '../../ui'

/** The faces and names of whoever follows a series that is not the manager's. */
export function HolderChip({ holders }: { holders: Profile[] }) {
  const names = holders.map((profile) => profile.name).join(', ')
  return (
    <span
      className="inline-flex max-w-full items-center self-start gap-space-xs rounded-full bg-surface-container-high py-0.5 pl-0.5 pr-space-sm text-label-sm text-on-surface-variant"
      title={`Followed by ${names}`}
    >
      <span className="flex -space-x-2">
        {holders.map((profile) => (
          <Avatar key={profile.id} avatar={profile.avatar} name={profile.name} size="sm" />
        ))}
      </span>
      <span className="truncate">{names}</span>
    </span>
  )
}
