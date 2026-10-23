import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api, type SourceResult, type SourceSearch } from '../../lib/api'
import { externalBase } from '../../lib/externalUrl'
import { useAsyncData } from '../../lib/useAsyncData'
import { Button, EmptyState, ErrorState, Icon, Skeleton } from '../../ui'
import { forgetSearches, recentSearches, rememberSearch } from './recentSearches'

/**
 * Every enabled source asked for one title.
 *
 * It searches on submit, never as you type: each search is a request to every
 * site, and a keystroke is not a decision to send one.
 */
export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q')?.trim() ?? ''
  const [draft, setDraft] = useState(query)
  const [recent, setRecent] = useState(recentSearches)

  const load = useCallback(
    () => (query ? api.searchSources(query) : Promise.resolve<SourceSearch | null>(null)),
    [query],
  )
  const { data, error, reload } = useAsyncData(load)

  // Kept on the address rather than on submit, so a search the palette opened
  // fills the field and joins the recent list the same as one typed here.
  useEffect(() => {
    if (!query) return
    setDraft(query)
    setRecent(rememberSearch(query))
  }, [query])

  function search(next: string) {
    const title = next.trim()
    if (title) setParams({ q: title })
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    search(draft)
  }

  return (
    <section className="flex flex-col gap-space-lg">
      <header className="flex flex-col gap-space-xs">
        <h1 className="text-headline-lg text-on-surface">Search sources</h1>
        <p className="text-body-md text-on-surface-variant">
          Every enabled source, asked at once. Nothing is added or downloaded from here.
        </p>
      </header>

      <form onSubmit={onSubmit} className="flex flex-col gap-space-sm sm:flex-row">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-3 top-3 text-outline">
            <Icon name="search" className="h-4 w-4" />
          </span>
          <input
            name="q"
            aria-label="Title"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="A title, in any language a source knows it by"
            autoFocus
            className="w-full rounded-lg bg-surface-container-low py-space-sm pl-9 pr-4 text-body-md text-on-surface placeholder:text-outline focus:bg-surface-container focus:outline-hidden"
          />
        </div>
        <Button type="submit" icon="search">
          Search
        </Button>
      </form>

      {recent.length > 0 && (
        <div className="flex flex-wrap items-center gap-space-xs">
          <span className="font-mono text-label-sm text-outline">Recent</span>
          {recent.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => search(item)}
              className="rounded-full bg-surface-container px-space-sm py-space-xs text-body-sm text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
            >
              {item}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setRecent(forgetSearches())}
            className="px-space-sm py-space-xs text-body-sm text-outline hover:text-on-surface"
          >
            Clear
          </button>
        </div>
      )}

      {query && <Results data={data} error={error} onRetry={reload} />}
    </section>
  )
}

function Results({
  data,
  error,
  onRetry,
}: {
  data: SourceSearch | null
  error: string | null
  onRetry: () => void
}) {
  if (error && !data) return <ErrorState title="The search failed" detail={error} onRetry={onRetry} />
  if (!data) {
    return (
      <div className="flex flex-col gap-space-xs">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-space-md">
      <p className="font-mono text-label-sm text-outline">
        {data.results.length} found across {data.searched} sources
      </p>
      {data.errors.length > 0 && (
        // Named, because a result list missing a site reads as complete
        // otherwise, and a title then looks unavailable when it is not.
        <p className="rounded-lg bg-warning-container/30 px-space-md py-space-sm text-body-sm text-on-surface">
          No answer from {data.errors.map((failure) => failure.site).join(', ')}.
        </p>
      )}
      {data.results.length === 0 ? (
        <EmptyState
          icon="search"
          title="No source has it"
          detail="Try the title another way: romanised, translated, or without a subtitle."
        />
      ) : (
        <ul className="flex flex-col gap-space-xs">
          {data.results.map((result) => (
            <li key={result.source_url}>
              <ResultRow result={result} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ResultRow({ result }: { result: SourceResult }) {
  // Every figure here is one the source served; a missing one is left out
  // rather than shown as a zero.
  const facts = [
    result.source_site,
    result.chapter_count ? `${result.chapter_count} ch` : null,
    result.year ? String(result.year) : null,
    `${Math.round(result.score * 100)}%`,
  ]
    .filter(Boolean)
    .join(' · ')

  const body = (
    <>
      <div className="h-16 w-11 shrink-0 overflow-hidden rounded bg-surface-container-highest">
        {result.cover_url && (
          <img
            src={result.cover_url}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-body-md text-on-surface">{result.title}</span>
        <span className="truncate font-mono text-label-sm text-outline">{facts}</span>
      </div>
      <span className="shrink-0 text-body-sm text-primary">
        {result.series_id !== null ? 'In your library' : 'Open on site'}
      </span>
    </>
  )

  const row =
    'flex items-center gap-space-sm rounded-lg bg-surface-container-low p-space-xs pr-space-md transition-colors hover:bg-surface-container-high'

  return result.series_id !== null ? (
    <Link to={`/series/${result.series_id}`} className={row}>
      {body}
    </Link>
  ) : (
    // Guarded like any address that came from outside: a source's parser hands
    // back whatever href the page held.
    <a href={externalBase(result.source_url) || undefined} target="_blank" rel="noreferrer" className={row}>
      {body}
    </a>
  )
}
