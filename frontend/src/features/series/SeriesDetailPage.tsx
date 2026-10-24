import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { backTo } from '../../lib/backTo'
import { Button, EmptyState, ErrorState, Icon, NoticeBar, Skeleton, Tabs } from '../../ui'
import { ChapterTable } from './ChapterTable'
import { CharacterGrid } from './CharacterGrid'
import { DownloadControls } from './DownloadControls'
import { ImportPanel } from './ImportPanel'
import { KindControl } from './KindControl'
import { MappingPanel } from './MappingPanel'
import { NotesPanel } from './NotesPanel'
import { ProseContents } from './ProseContents'
import { ProgressManager } from './ProgressManager'
import { ReadingFrequency } from './ReadingFrequency'
import { ScoreStrip } from './ScoreStrip'
import { SeriesHeader } from './SeriesHeader'
import { SimilarWorks } from './SimilarWorks'
import { SynopsisPanel } from './SynopsisPanel'
import { VolumesPanel } from './VolumesPanel'
import { SyncTargets } from './SyncTargets'
import { totalChapters, useSeriesDetail } from './useSeriesDetail'

type Panel = 'chapters' | 'notes' | 'characters' | 'import'

// The mockup's own geometry: a twelve-column hero with the cover on three,
// then a two-column body. Three things the mockup shows are deliberately absent
// here — per-chapter release dates, page counts, and a ComicInfo validation
// badge. No provider serves any of them, and an invented figure that fills a
// gap in a mockup is worse than the gap. The release cadence it also shows is
// in the header now, read from when chapters arrived here rather than invented. The weekday
// reading chart was deferred rather than dropped, and it is built now that
// `progress_event` has landed.
export function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>()
  const seriesId = Number(id)
  const {
    detail,
    queuedChapter,
    refusal,
    notFound,
    error,
    reload,
    toggleAutoDownload,
    setKind,
    download,
    research,
    remap,
    setProgress,
    setListStatus,
    saveNotes,
    bookmark,
  } = useSeriesDetail(seriesId)
  const [panel, setPanel] = useState<Panel>('chapters')
  // The screen that linked here says where "back" goes; the library stands in
  // when nothing did, which is what a pasted address or a reload amounts to.
  const back = backTo(useLocation())

  if (notFound) {
    return (
      <EmptyState
        icon="warning"
        title="Series not found"
        detail={`It may have been removed. Head back to the ${back.label} and pick another one.`}
        action={
          <Link to={back.to}>
            <Button variant="surface" icon="book">
              Back to {back.label}
            </Button>
          </Link>
        }
      />
    )
  }

  if (!detail && error) {
    return <ErrorState title="Couldn't load this series" detail={error} onRetry={reload} />
  }

  if (!detail) {
    return (
      <div className="flex flex-col gap-space-lg">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  const { series, metadata, mapping, chapters, entries } = detail
  const total = totalChapters(detail)
  const prose = series.kind === 'prose'
  const volumeProgress = Math.max(0, ...entries.map((entry) => entry.user_progress_volume ?? 0))

  return (
    <div className="flex flex-col gap-space-xl">
      <Link
        to={back.to}
        className="flex w-fit items-center gap-space-xs text-body-sm text-on-surface-variant hover:text-on-surface"
      >
        <Icon name="chevron" className="h-4 w-4 rotate-90" />
        Back to {back.label}
      </Link>

      {/* A page already showing real data stays showing it — a failed
          background refresh says so here instead of collapsing to the
          not-found or first-load error screens above. */}
      {error && (
        <NoticeBar tone="error" text={`Couldn't refresh this series: ${error}`} onRetry={reload} />
      )}

      <section className="grid grid-cols-1 items-start gap-space-xl lg:grid-cols-12">
        <div className="aspect-[2/3] w-56 shrink-0 overflow-hidden rounded-xl bg-surface-container-highest shadow-card sm:w-64 lg:col-span-3 lg:w-full">
          {series.cover_url && (
            <img
              src={series.cover_url}
              alt={`Cover of ${series.title}`}
              className="h-full w-full object-cover"
            />
          )}
        </div>
        <SeriesHeader
          series={series}
          metadata={metadata}
          komgaBaseUrl={detail.komga_public_url}
          rhythmDays={detail.rhythm_days}
        />
      </section>

      <ScoreStrip metadata={metadata} />

      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_360px]">
        <div className="flex min-w-0 flex-col gap-space-lg">
          <ProgressManager
            detail={detail}
            total={total}
            minutesPerChapter={detail.reading_minutes_per_chapter}
            queued={queuedChapter}
            refusal={refusal}
            onProgress={setProgress}
            onStatus={setListStatus}
            onTracked={reload}
          />

          <ReadingFrequency frequency={detail.reading_frequency} />

          <section className="flex flex-col gap-space-md">
            <Tabs
              options={[
                // A novel is read by the volume, so its tab lists both.
                prose
                  ? { value: 'chapters', label: 'Contents', count: null }
                  : { value: 'chapters', label: 'Chapters', count: chapters.length },
                { value: 'notes', label: 'Your note' },
                // A count only when the enrichment has landed; "(0)" while it
                // is still queued would read as "this manga has no characters".
                {
                  value: 'characters',
                  label: 'Characters',
                  count: metadata.characters.length || null,
                },
                // Only a prose series takes files: the import writes prose EPUBs.
                ...(series.kind === 'prose' ? [{ value: 'import' as const, label: 'Import files' }] : []),
              ]}
              value={panel}
              onChange={setPanel}
            />
            <div hidden={panel !== 'chapters'}>
              {prose ? (
                <ProseContents
                  volumes={detail.volumes}
                  chapters={chapters}
                  progress={series.progress}
                  volumeProgress={volumeProgress}
                  onBookmark={bookmark}
                />
              ) : (
                <ChapterTable
                  chapters={chapters}
                  komgaBaseUrl={detail.komga_public_url}
                  progress={series.progress}
                  prose={false}
                  onBookmark={bookmark}
                />
              )}
            </div>
            <div hidden={panel !== 'notes'}>
              {/* Mounted even while hidden: NotesPanel holds an unsaved draft in local
                  state, and unmounting the inactive tab would throw it away on a tab
                  click — the same loss the draft-preservation flag exists to prevent. */}
              <NotesPanel metadata={metadata} onSave={saveNotes} />
            </div>
            {series.kind === 'prose' && (
              // Mounted while hidden, like NotesPanel: a tab click must not lose a
              // review in progress or the import it is following.
              <div hidden={panel !== 'import'}>
                <ImportPanel seriesId={series.id} />
              </div>
            )}
            <div hidden={panel !== 'characters'}>
              <CharacterGrid
                characters={metadata.characters}
                providers={metadata.providers}
                enrichedAt={metadata.enriched_at}
              />
            </div>
          </section>
        </div>

        <aside className="flex flex-col gap-space-md">
          <MappingPanel
            seriesId={series.id}
            mapping={mapping}
            local={series.state === 'local'}
            onResearch={research}
            onRemap={remap}
          />
          {/* A novel's volumes are its contents, listed in the main column. */}
          {!prose && (
            <VolumesPanel volumes={detail.volumes} komgaBaseUrl={detail.komga_public_url} />
          )}
          <SyncTargets entries={entries} />
          <KindControl kind={series.kind} onChange={setKind} />
          <DownloadControls
            autoDownload={series.auto_download}
            onToggleAutoDownload={toggleAutoDownload}
            onDownload={download}
            onQueued={reload}
          />
          <SynopsisPanel metadata={metadata} />
          <SimilarWorks items={metadata.similar} />
        </aside>
      </div>
    </div>
  )
}
