import type { Profile, Series } from '../../lib/api'
import { CoverCard } from './CoverCard'

// grid-cols-2 is the mobile default; sm: swaps to an auto-fill track so wide
// viewports pack as many 160-220px posters as fit instead of stretching two.
export function SeriesGrid({
  series,
  pending,
  onIncrement,
  selected,
  onToggleSelect,
  holdersOf,
}: {
  series: Series[]
  /** Series whose last +1 is queued and not yet written. */
  pending: ReadonlySet<number>
  onIncrement: (id: number, next: number) => Promise<void>
  /** Marked for a bulk action. Empty when nothing is selected. */
  selected?: ReadonlySet<number>
  onToggleSelect?: (id: number) => void
  /** Who follows a series that is not the manager's; null for none to show. */
  holdersOf?: (series: Series) => Profile[] | null
}) {
  return (
    <div className="grid grid-cols-2 gap-5 sm:grid-cols-[repeat(auto-fill,minmax(160px,220px))]">
      {series.map((row) => (
        <CoverCard
          key={row.id}
          series={row}
          pending={pending.has(row.id)}
          onIncrement={onIncrement}
          selected={selected?.has(row.id) ?? false}
          onToggleSelect={onToggleSelect}
          holdersOf={holdersOf}
        />
      ))}
    </div>
  )
}
