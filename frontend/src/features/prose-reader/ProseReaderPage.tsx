import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  api,
  messageOf,
  type ProseKind,
  type ProseManifest,
  type ProsePrefs,
  type ProseSection,
} from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { Icon, IconButton, ReaderMessage } from '../../ui'
import { EndOfBook } from './EndOfBook'
import { ProseContentsSheet } from './ProseContentsSheet'
import { ProseSettings } from './ProseSettings'
import { PAGE, SIZE } from './theme'
import { scrollToPlace, useProsePosition } from './useProsePosition'

// Long enough for the illustrations above the saved place to load, so the
// place is measured on the page as it will finally sit; short enough that a
// slow image never keeps the reader at the top.
const IMAGE_WAIT_MS = 3000
const SECTIONS_AT_ONCE = 4

/** A fresh reader per book: nothing of the last one's place may leak in. */
export function ProseReaderRoute() {
  const { kind, id } = useParams()
  if (kind !== 'chapter' && kind !== 'volume') {
    return <ReaderMessage title="Nothing to read here" backTo="/library" />
  }
  return <ProseReaderPage key={`${kind}-${id}`} kind={kind} id={Number(id)} />
}

/** A title that only restates the number ("Volume 2" on volume 2) is no title. */
function ownTitle(title: string | null, number: number): string | null {
  if (!title) return null
  return new RegExp(`^(vol(ume)?|ch(apter)?)\\.?\\s*0*${number}$`, 'i').test(title.trim())
    ? null
    : title
}

async function imagesSettled(column: HTMLElement): Promise<void> {
  const pending = [...column.querySelectorAll('img')]
    .filter((image) => !image.complete)
    .map((image) => new Promise((done) => {
      image.addEventListener('load', done, { once: true })
      image.addEventListener('error', done, { once: true })
    }))
  await Promise.race([
    Promise.all(pending),
    new Promise((done) => window.setTimeout(done, IMAGE_WAIT_MS)),
  ])
}

function ProseReaderPage({ kind, id }: { kind: ProseKind; id: number }) {
  const navigate = useNavigate()
  const load = useCallback(() => api.proseManifest(kind, id), [kind, id])
  const { data: manifest, error, notFound } = useAsyncData(load)

  const [sections, setSections] = useState<ProseSection[] | null>(null)
  const [sectionsError, setSectionsError] = useState<string | null>(null)
  const [prefs, setPrefs] = useState<ProsePrefs | null>(null)
  const [prefsError, setPrefsError] = useState<string | null>(null)
  const [panel, setPanel] = useState<'settings' | 'contents' | null>(null)
  const [chrome, setChrome] = useState(true)
  const [ready, setReady] = useState(false)
  const [finish, setFinish] = useState<'idle' | 'busy' | 'done' | 'failed'>('idle')
  const [column, setColumn] = useState<HTMLElement | null>(null)
  const [progress, setProgress] = useState(0)
  const lastY = useRef(0)

  // The whole book as one document: a volume is a few hundred kilobytes of
  // text, and a single page is what lets the browser scroll it, find in it and
  // keep its place without this screen paging anything. Fetched a few
  // sections at a time, so a book of hundreds does not open hundreds of
  // requests against the api at once.
  useEffect(() => {
    if (!manifest) return
    setPrefs(manifest.prefs)
    let cancelled = false
    void (async () => {
      const loaded: ProseSection[] = []
      for (let start = 0; start < manifest.sections.length; start += SECTIONS_AT_ONCE) {
        const batch = manifest.sections.slice(start, start + SECTIONS_AT_ONCE)
        loaded.push(
          ...(await Promise.all(batch.map((section) => api.proseSection(kind, id, section.index)))),
        )
        if (cancelled) return
      }
      setSections(loaded)
    })().catch((failure: unknown) => {
      if (!cancelled) setSectionsError(messageOf(failure))
    })
    return () => {
      cancelled = true
    }
  }, [manifest, kind, id])

  // Restored once, after the text and its illustrations have laid out.
  useEffect(() => {
    if (!manifest || !sections || !column || ready) return
    let cancelled = false
    void imagesSettled(column).then(() => {
      if (cancelled) return
      const place = manifest.position
      if (place) scrollToPlace(column, place.section, place.fraction)
      else window.scrollTo({ top: 0 })
      setReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [manifest, sections, column, ready])

  const current = useProsePosition(manifest?.series.id ?? null, kind, id, column, ready)
  const place = useRef(current)
  place.current = current

  // A new text size reflows every line above the reader; without this the
  // same scroll offset lands pages away from where they were reading.
  const size = prefs?.font_size
  useEffect(() => {
    if (!ready || !column) return
    const { section, fraction } = place.current
    requestAnimationFrame(() => scrollToPlace(column, section, fraction))
  }, [size, ready, column])

  // The bar steps aside while reading forward and comes back on the way up,
  // the way e-readers and mobile browsers do.
  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY
      const height = document.documentElement.scrollHeight - window.innerHeight
      setProgress(height > 0 ? Math.min(1, y / height) : 0)
      if (Math.abs(y - lastY.current) < 8) return
      setChrome(y < lastY.current || y < 64)
      lastY.current = y
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const changePrefs = (next: ProsePrefs) => {
    setPrefs(next)
    setPrefsError(null)
    api.saveProsePrefs(next).catch((failure: unknown) => setPrefsError(messageOf(failure)))
  }

  const markRead = useCallback(async (): Promise<boolean> => {
    if (finish === 'done') return true
    setFinish('busy')
    try {
      if (kind === 'volume') await api.completeVolume(id)
      else await api.completeChapter(id)
      setFinish('done')
      return true
    } catch {
      setFinish('failed')
      return false
    }
  }, [finish, kind, id])

  const goNext = async (book: ProseManifest['next']) => {
    if (!book) return
    // Moving on is saying this one is finished; a failure to record that
    // leaves the reader here to try again rather than losing it silently.
    if (await markRead()) navigate(`/read/prose/${book.kind}/${book.id}`)
  }

  const back = manifest ? `/series/${manifest.series.id}` : '/library'
  if (notFound) {
    return (
      <ReaderMessage
        title="This book is not in the library"
        detail="Its file may have moved or not be downloaded yet."
        backTo={back}
      />
    )
  }
  if (error && !manifest) {
    return <ReaderMessage title="Could not open this book" detail={error} backTo={back} />
  }
  if (sectionsError) {
    return <ReaderMessage title="Could not read this book" detail={sectionsError} backTo={back} />
  }
  if (!manifest || !prefs) return <ReaderMessage title="Opening…" backTo={back} />

  const title = ownTitle(manifest.title, manifest.number)
  const heading = `${manifest.kind === 'volume' ? 'Vol.' : 'Ch'} ${manifest.number}${
    title ? ` · ${title}` : ''
  }`
  // A book written as one section has the whole book's name as its only
  // entry, which would repeat the series beside itself.
  const sectionTitle =
    manifest.sections.length > 1 ? manifest.sections[current.section]?.title : null

  return (
    // flow-root: the end card's bottom margin would otherwise collapse out of
    // the page and show the app's own background below it.
    <div className={`flow-root min-h-screen ${PAGE[prefs.theme]}`}>
      <header
        className={`fixed inset-x-0 top-0 z-30 flex items-center gap-space-sm bg-surface-container/95 px-space-md py-space-sm text-on-surface shadow-card transition-transform duration-200 ${
          chrome ? 'translate-y-0' : '-translate-y-full'
        }`}
      >
        <Link
          to={back}
          aria-label="Back to the series"
          className="rounded-lg p-space-xs text-outline hover:bg-surface-container-high hover:text-on-surface"
        >
          <Icon name="arrow_back" className="h-5 w-5" />
        </Link>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-title-md">{manifest.series.title}</span>
          <span className="truncate font-mono text-label-sm text-outline">
            {heading}
            {sectionTitle ? ` · ${sectionTitle}` : ''}
          </span>
        </div>
        <IconButton icon="list" label="Contents" onClick={() => setPanel('contents')} />
        <IconButton icon="settings" label="Reading settings" onClick={() => setPanel('settings')} />
      </header>

      <div className="fixed inset-x-0 bottom-0 z-30 h-0.5 bg-current/10">
        <div className="h-full bg-primary" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>

      <main
        ref={setColumn}
        className={`prose-text mx-auto max-w-prose-column px-space-lg pt-prose-bar pb-space-xl font-reading ${SIZE[prefs.font_size] ?? SIZE[3]}`}
        // Taps in the text bring the bar back, as on a phone's e-reader.
        onClick={() => setChrome(true)}
      >
        {sections === null ? (
          <p className="text-center font-sans text-body-md opacity-70">Loading the text…</p>
        ) : (
          sections.map((section) => (
            <section
              key={section.index}
              data-section={section.index}
              // Built server-side from an allowlist of tags with every attribute
              // dropped but an image's own src and alt: nothing here can run.
              dangerouslySetInnerHTML={{ __html: section.html }}
            />
          ))
        )}
      </main>

      {sections !== null && (
        <EndOfBook
          kind={manifest.kind}
          next={manifest.next}
          seriesId={manifest.series.id}
          state={finish}
          onFinish={() => void markRead()}
          onNext={() => void goNext(manifest.next)}
        />
      )}

      {panel === 'settings' && (
        <ProseSettings
          prefs={prefs}
          error={prefsError}
          onChange={changePrefs}
          onClose={() => setPanel(null)}
        />
      )}
      {panel === 'contents' && column && (
        <ProseContentsSheet
          sections={manifest.sections}
          current={current.section}
          onPick={(index) => {
            setPanel(null)
            scrollToPlace(column, index, 0)
          }}
          onClose={() => setPanel(null)}
        />
      )}
    </div>
  )
}
