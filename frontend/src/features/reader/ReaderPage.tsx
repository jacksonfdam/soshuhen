import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api, readerPageUrl, type ReaderPrefs } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { ChapterPanel } from './ChapterPanel'
import { DesktopChrome } from './DesktopChrome'
import { EndOfChapter } from './EndOfChapter'
import { clampPage, spreadOf, spreads } from './lib/spreads'
import { BACKGROUND } from './lib/styles'
import { usePositionSaver } from './lib/usePositionSaver'
import { usePreload } from './lib/usePreload'
import { useReaderKeys } from './lib/useReaderKeys'
import { PagedView, type Zone } from './PagedView'
import { ReaderMessage } from './ReaderMessage'
import { SettingsPanel } from './SettingsPanel'
import { StripView } from './StripView'
import { TabletChrome } from './TabletChrome'

const PRELOAD_AHEAD = 3

export type Panel = 'settings' | 'chapters' | null

export function ReaderPage() {
  const chapterId = Number(useParams().chapterId)
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const load = useCallback(() => api.readerManifest(chapterId), [chapterId])
  const { data: manifest, error, notFound } = useAsyncData(load)

  const [prefs, setPrefs] = useState<ReaderPrefs | null>(null)
  const [page, setPage] = useState(0)
  const [atEnd, setAtEnd] = useState(false)
  const [chromeVisible, setChromeVisible] = useState(true)
  const [panel, setPanel] = useState<Panel>(null)
  const [prefsError, setPrefsError] = useState<string | null>(null)
  const completed = useRef(new Set<number>())

  const save = usePositionSaver(manifest?.series.id ?? null, manifest?.chapter.id ?? null)

  // Once per manifest: the address wins over the saved position, so a link to
  // a page opens that page. The address is read here and not tracked, because
  // every page turn rewrites it.
  useEffect(() => {
    if (!manifest) return
    setPrefs(manifest.prefs)
    const requested = params.get('page')
    const start = clampPage(
      requested !== null ? Number(requested) : (manifest.position ?? 0),
      manifest.page_count,
    )
    setPage(start)
    setAtEnd(false)
    save(start, { immediately: true })
  }, [manifest])

  const mode = prefs?.mode ?? 'paged_rtl'
  const rtl = mode === 'paged_rtl'
  const strip = mode === 'long_strip'
  const groups = useMemo(() => spreads(manifest?.page_count ?? 0, mode), [manifest, mode])
  const step = spreadOf(groups, page)

  const goTo = useCallback(
    (next: number) => {
      if (!manifest) return
      const target = clampPage(next, manifest.page_count)
      setPage(target)
      setAtEnd(false)
      save(target)
      setParams({ page: String(target) }, { replace: true })
    },
    [manifest, save, setParams],
  )

  const openChapter = useCallback((id: number) => navigate(`/read/${id}?page=0`), [navigate])

  const finish = useCallback(() => {
    if (!manifest || completed.current.has(manifest.chapter.id)) return
    const id = manifest.chapter.id
    completed.current.add(id)
    // A failure moves nothing and is retried by finishing the chapter again;
    // it does not deserve an interruption.
    void api.completeChapter(id).catch(() => completed.current.delete(id))
  }, [manifest])

  const forward = useCallback(() => {
    if (!manifest) return
    if (strip) {
      window.scrollBy({ top: window.innerHeight * 0.9, behavior: 'smooth' })
      return
    }
    if (atEnd) {
      if (manifest.next) openChapter(manifest.next.id)
      return
    }
    if (step + 1 < groups.length) goTo(groups[step + 1][0])
    else {
      setAtEnd(true)
      finish()
    }
  }, [manifest, strip, atEnd, step, groups, goTo, openChapter, finish])

  const back = useCallback(() => {
    if (!manifest) return
    if (strip) {
      window.scrollBy({ top: -window.innerHeight * 0.9, behavior: 'smooth' })
      return
    }
    if (atEnd) setAtEnd(false)
    else if (step > 0) goTo(groups[step - 1][0])
    else if (manifest.previous) openChapter(manifest.previous.id)
  }, [manifest, strip, atEnd, step, groups, goTo, openChapter])

  const changePrefs = useCallback(
    (next: Omit<ReaderPrefs, 'custom'>) => {
      if (!manifest || !prefs) return
      const before = prefs
      setPrefs({ ...next, custom: true })
      setPrefsError(null)
      api
        .saveReaderPrefs(manifest.series.id, next)
        .then(setPrefs)
        .catch((failure: unknown) => {
          setPrefs(before)
          setPrefsError(failure instanceof Error ? failure.message : 'Could not save.')
        })
    },
    [manifest, prefs],
  )

  const makeDefault = useCallback(() => {
    if (!prefs) return
    setPrefsError(null)
    api
      .saveReaderDefaults({ mode: prefs.mode, scale: prefs.scale, background: prefs.background })
      .catch((failure: unknown) => {
        setPrefsError(failure instanceof Error ? failure.message : 'Could not save.')
      })
  }, [prefs])

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined)
    else void document.documentElement.requestFullscreen().catch(() => undefined)
  }, [])

  useReaderKeys({
    left: rtl ? forward : back,
    right: rtl ? back : forward,
    forward,
    back,
    previousChapter: () => {
      if (manifest?.previous) openChapter(manifest.previous.id)
    },
    nextChapter: () => {
      if (manifest?.next) openChapter(manifest.next.id)
    },
    fullscreen: toggleFullscreen,
    escape: () => setPanel(null),
  })

  // A paged mode shows each page from its top; the browser would otherwise
  // keep the scroll offset of a tall page on the next one.
  useEffect(() => {
    if (!strip) window.scrollTo({ top: 0 })
  }, [page, atEnd, strip])

  const visibleLast = groups[step]?.at(-1) ?? page
  const preload = useMemo(() => {
    if (!manifest) return []
    const urls: string[] = []
    const last = Math.min(visibleLast + PRELOAD_AHEAD, manifest.page_count - 1)
    for (let index = visibleLast + 1; index <= last; index++) {
      urls.push(readerPageUrl(manifest.chapter.id, index))
    }
    if (manifest.next && manifest.page_count - visibleLast <= PRELOAD_AHEAD) {
      for (let index = 0; index < PRELOAD_AHEAD; index++) {
        urls.push(readerPageUrl(manifest.next.id, index))
      }
    }
    return urls
  }, [manifest, visibleLast])
  usePreload(preload)

  if (notFound) return <ReaderMessage title="This chapter no longer exists" backTo="/library" />
  if (error && !manifest) {
    return <ReaderMessage title="This chapter cannot be read" detail={error} backTo="/library" />
  }
  if (!manifest || !prefs) return <ReaderMessage title="Opening…" backTo="/library" />

  function onZone(zone: Zone) {
    if (zone === 'center') setChromeVisible((visible) => !visible)
    else if (zone === 'left') (rtl ? forward : back)()
    else (rtl ? back : forward)()
  }

  const toggleChrome = () => setChromeVisible((visible) => !visible)
  // Down a strip a page is a place in the scroll, not a state to set.
  const seek = (index: number) => {
    if (strip) document.querySelector(`[data-index="${index}"]`)?.scrollIntoView()
    else goTo(index)
  }
  const end = (
    <EndOfChapter
      current={manifest.chapter}
      next={manifest.next}
      seriesId={manifest.series.id}
      onNext={() => {
        if (manifest.next) openChapter(manifest.next.id)
      }}
    />
  )

  return (
    <main className={`min-h-screen w-full ${BACKGROUND[prefs.background]}`}>
      {strip ? (
        <StripView
          chapterId={manifest.chapter.id}
          pageCount={manifest.page_count}
          scale={prefs.scale}
          initialPage={page}
          onPage={(index) => {
            setPage(index)
            save(index)
          }}
          onEnd={finish}
          onTap={toggleChrome}
          end={end}
        />
      ) : atEnd ? (
        <div onClick={toggleChrome}>{end}</div>
      ) : (
        <PagedView
          chapterId={manifest.chapter.id}
          group={groups[step] ?? [page]}
          scale={prefs.scale}
          rtl={rtl}
          onZone={onZone}
        />
      )}
      <TabletChrome
        manifest={manifest}
        page={page}
        rtl={rtl}
        visible={chromeVisible}
        onSeek={seek}
        onOpenChapter={openChapter}
        onPanel={setPanel}
      />
      <DesktopChrome
        manifest={manifest}
        page={page}
        rtl={rtl}
        strip={strip}
        onSeek={seek}
        onOpenChapter={openChapter}
        onPanel={setPanel}
        onFullscreen={toggleFullscreen}
      />
      {panel === 'settings' && (
        <SettingsPanel
          prefs={prefs}
          error={prefsError}
          onChange={changePrefs}
          onMakeDefault={makeDefault}
          onClose={() => setPanel(null)}
        />
      )}
      {panel === 'chapters' && (
        <ChapterPanel
          seriesId={manifest.series.id}
          currentId={manifest.chapter.id}
          onOpen={(id) => {
            setPanel(null)
            openChapter(id)
          }}
          onClose={() => setPanel(null)}
        />
      )}
    </main>
  )
}
