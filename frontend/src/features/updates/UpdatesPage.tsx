import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type UpdateChapter } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useUrlState } from '../../lib/useUrlState'
import { EmptyState, ErrorState, Icon, SelectField, Skeleton } from '../../ui'

type Period = '7' | '30' | '90'

const PERIODS: { value: Period; label: string }[] = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
]

interface SeriesGroup {
  seriesId: number
  title: string
  prose: boolean
  chapters: UpdateChapter[]
}

interface DayGroup {
  key: string
  label: string
  series: SeriesGroup[]
}

// The viewer's own calendar day, not the server's: a chapter found at 01:00
// UTC belongs to the evening before for anyone west of Greenwich.
function dayKey(iso: string): string {
  const date = new Date(iso)
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function dayLabel(iso: string): string {
  const date = new Date(iso)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (dayKey(iso) === dayKey(today.toISOString())) return 'Today'
  if (dayKey(iso) === dayKey(yesterday.toISOString())) return 'Yesterday'
  return date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
}

function groupByDay(chapters: UpdateChapter[]): DayGroup[] {
  const days: DayGroup[] = []
  for (const chapter of chapters) {
    const key = dayKey(chapter.discovered_at)
    let day = days.at(-1)
    if (day?.key !== key) {
      day = { key, label: dayLabel(chapter.discovered_at), series: [] }
      days.push(day)
    }
    let series = day.series.find((entry) => entry.seriesId === chapter.series_id)
    if (!series) {
      series = {
        seriesId: chapter.series_id,
        title: chapter.series_title,
        prose: chapter.prose,
        chapters: [],
      }
      day.series.push(series)
    }
    series.chapters.push(chapter)
  }
  return days
}

/**
 * New chapters, by the day they were found.
 *
 * The bell says that something arrived; this says what, and keeps saying it
 * after the notification is read and gone.
 */
export function UpdatesPage() {
  const [period, setPeriod] = useUrlState<Period>('days', '30', ['7', '30', '90'])
  const load = useCallback(() => api.updates(Number(period)), [period])
  const { data, error, reload } = useAsyncData(load)
  const days = useMemo(() => (data ? groupByDay(data.chapters) : []), [data])

  return (
    <section className="flex flex-col gap-space-lg">
      <header className="flex flex-wrap items-end justify-between gap-space-md">
        <div className="flex flex-col gap-space-xs">
          <h1 className="text-headline-lg text-on-surface">New chapters</h1>
          <p className="text-body-md text-on-surface-variant">
            Found at a source after the series was already followed. A series' back catalogue is
            never news.
          </p>
        </div>
        <SelectField label="Show" value={period} options={PERIODS} onChange={setPeriod} />
      </header>

      {error && !data ? (
        <ErrorState detail={error} onRetry={reload} />
      ) : !data ? (
        <div className="flex flex-col gap-space-sm">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
      ) : days.length === 0 ? (
        <EmptyState
          icon="bell"
          title="Nothing new in this period"
          detail="Chapters a discovery run finds for a series you follow appear here, by day."
        />
      ) : (
        <>
          {days.map((day) => (
            <div key={day.key} className="flex flex-col gap-space-sm">
              <h2 className="font-mono text-label-md text-outline">{day.label}</h2>
              <ul className="flex flex-col gap-space-xs">
                {day.series.map((series) => (
                  <li key={series.seriesId}>
                    <SeriesRow series={series} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {data.truncated && (
            <p className="font-mono text-label-sm text-outline">
              Only the latest {data.chapters.length} chapters are shown.
            </p>
          )}
        </>
      )}
    </section>
  )
}

function SeriesRow({ series }: { series: SeriesGroup }) {
  // A missing cover leaves the tile empty rather than a broken image.
  const [cover, setCover] = useState(true)
  // Ascending inside a row: the run of numbers reads the way it will be read.
  const chapters = [...series.chapters].sort((a, b) => a.number - b.number)

  return (
    <div className="flex items-center gap-space-sm rounded-lg bg-surface-container-low p-space-xs pr-space-md">
      <Link
        to={`/series/${series.seriesId}`}
        className="flex h-16 w-11 shrink-0 items-center justify-center overflow-hidden rounded bg-surface-container-highest text-on-surface-variant"
      >
        {cover ? (
          <img
            src={`/api/series/${series.seriesId}/cover`}
            alt=""
            loading="lazy"
            onError={() => setCover(false)}
            className="h-full w-full object-cover"
          />
        ) : (
          <Icon name="book" />
        )}
      </Link>
      <div className="flex min-w-0 flex-1 flex-col gap-space-xs">
        <Link
          to={`/series/${series.seriesId}`}
          className="truncate text-body-md text-on-surface hover:underline"
        >
          {series.title}
        </Link>
        <div className="flex flex-wrap gap-space-xs">
          {chapters.map((chapter) =>
            series.prose ? (
              <span
                key={chapter.id}
                className="rounded-full bg-surface-container px-space-sm py-0.5 font-mono text-label-sm text-on-surface-variant"
              >
                Ch {formatChapter(chapter.number)}
              </span>
            ) : (
              <Link
                key={chapter.id}
                to={`/read/${chapter.id}`}
                title={chapter.title ?? undefined}
                className="rounded-full bg-primary/[0.12] px-space-sm py-0.5 font-mono text-label-sm text-primary transition-colors hover:bg-primary/20"
              >
                Ch {formatChapter(chapter.number)}
              </Link>
            ),
          )}
        </div>
      </div>
    </div>
  )
}
