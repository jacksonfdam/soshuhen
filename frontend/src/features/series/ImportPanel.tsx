import { useRef, useState, type DragEvent } from 'react'

import {
  ApiError,
  api,
  messageOf,
  type ImportEdition,
  type ImportFile,
  type ImportOverride,
  type ImportPreview,
} from '../../lib/api'
import { useJobEvents } from '../../lib/useEvents'
import { Badge, Button, Icon, NoticeBar, ProgressBar, SegmentedControl } from '../../ui'

type Stage =
  | { step: 'idle' }
  | { step: 'reading' }
  | { step: 'review'; preview: ImportPreview }
  | { step: 'importing'; jobId: number | null; pct: number; files: ImportFile[] }
  | { step: 'done'; files: ImportFile[] }

const ACCEPTED = ['application/pdf', 'application/epub+zip']

const EDITIONS: { value: ImportEdition; label: string }[] = [
  { value: 'web', label: 'Web novel' },
  { value: 'light', label: 'Light novel' },
]

// Every count here is read from the plan the server answered with; the panel
// never guesses what a file will become.
function summary(files: ImportFile[]): string {
  const ready = files.filter((file) => file.status === 'ready')
  const chapters = ready.filter((f) => f.edition === 'web').reduce((n, f) => n + f.chapters.length, 0)
  const volumes = ready.filter((f) => f.edition === 'light').length
  return `${ready.length} files · ${chapters} chapters · ${volumes} whole volumes`
}

function readAs(file: ImportFile): string {
  if (file.status === 'unreadable') return '—'
  if (file.edition === 'light') return 'Whole volume'
  if (file.chapters.length === 0) return 'No chapters'
  return `Ch. ${file.chapters[0]}–${file.chapters[file.chapters.length - 1]} (${file.chapters.length})`
}

function becomes(file: ImportFile): string {
  if (file.outputs.length === 0) return '—'
  if (file.outputs.length === 1) return file.outputs[0]
  return `${file.outputs[0]} … ${file.outputs[file.outputs.length - 1]}`
}

function statusBadge(file: ImportFile, replacing: boolean) {
  if (file.status === 'ready') return <Badge tone="secondary">Ready</Badge>
  if (file.status === 'exists') {
    return <Badge tone={replacing ? 'warning' : 'tertiary'}>{replacing ? 'Replace' : 'Already in library'}</Badge>
  }
  if (file.status === 'duplicate') return <Badge tone="tertiary">Duplicate</Badge>
  return <Badge tone="error">{file.status === 'conflict' ? 'Conflict' : 'Unreadable'}</Badge>
}

export function ImportPanel({ seriesId }: { seriesId: number }) {
  const [stage, setStage] = useState<Stage>({ step: 'idle' })
  const [overrides, setOverrides] = useState<Record<string, ImportOverride>>({})
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const picker = useRef<HTMLInputElement>(null)

  useJobEvents((event) => {
    if (stage.step !== 'importing' || stage.jobId === null || event.job_id !== stage.jobId) return
    if (event.event === 'job.progress') {
      setStage({ ...stage, pct: event.pct ?? stage.pct })
    } else if (event.event === 'job.failed') {
      setError(event.message || 'The import failed.')
      setStage({ step: 'idle' })
    } else {
      setStage({ step: 'done', files: stage.files })
    }
  })

  async function read(files: File[]) {
    // A PDF is split into chapters; an EPUB is one light novel volume, placed as it is.
    const books = files.filter((file) => /\.(pdf|epub)$/i.test(file.name) || ACCEPTED.includes(file.type))
    if (books.length === 0) return
    setError(null)
    setOverrides({})
    setStage({ step: 'reading' })
    try {
      setStage({ step: 'review', preview: await api.previewImport(seriesId, books) })
    } catch (failure) {
      setError(messageOf(failure))
      setStage({ step: 'idle' })
    }
  }

  function override(file: ImportFile, change: Partial<ImportOverride>) {
    setOverrides((current) => ({
      ...current,
      [file.sha256]: {
        volume: current[file.sha256]?.volume ?? null,
        edition: current[file.sha256]?.edition ?? null,
        replace: current[file.sha256]?.replace ?? false,
        ...change,
      },
    }))
  }

  async function confirm(preview: ImportPreview) {
    setError(null)
    try {
      const answer = await api.confirmImport(seriesId, preview.token, overrides)
      const files = answer.files.filter((file) => file.status === 'ready')
      setStage({ step: 'importing', jobId: answer.job_id, pct: 0, files })
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 410) {
        setError('The uploaded files are gone. Upload again.')
        setStage({ step: 'idle' })
        return
      }
      setError(messageOf(failure))
    }
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault()
    setDragging(false)
    void read(Array.from(event.dataTransfer.files))
  }

  const notice = error && <NoticeBar tone="error" text={error} />

  if (stage.step === 'importing' || stage.step === 'done') {
    const done = stage.step === 'done'
    return (
      <section className="flex flex-col gap-space-sm">
        {notice}
        <p className="text-body-sm text-on-surface">
          {done ? 'Imported. Komga is scanning the new files.' : `Importing ${summary(stage.files)}…`}
        </p>
        {!done && <ProgressBar value={stage.pct} max={100} />}
        {done && (
          <div>
            <Button onClick={() => setStage({ step: 'idle' })}>Import more files</Button>
          </div>
        )}
      </section>
    )
  }

  if (stage.step === 'review') {
    const { preview } = stage
    const files = preview.files.map((file) => ({ file, choice: overrides[file.sha256] }))
    const importable = files.filter(
      ({ file, choice }) => file.status === 'ready' || (file.status === 'exists' && choice?.replace),
    ).length
    return (
      <section className="flex flex-col gap-space-sm">
        {notice}
        <p className="font-mono text-label-sm text-on-surface-variant">{summary(preview.files)}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-body-sm">
            <thead className="font-mono text-label-sm text-on-surface-variant">
              <tr>
                <th className="py-space-xs pr-space-sm">File</th>
                <th className="py-space-xs pr-space-sm">Volume</th>
                <th className="py-space-xs pr-space-sm">Edition</th>
                <th className="py-space-xs pr-space-sm">Read as</th>
                <th className="py-space-xs pr-space-sm">Becomes</th>
                <th className="py-space-xs">Status</th>
              </tr>
            </thead>
            <tbody>
              {files.map(({ file, choice }) => (
                <tr key={file.sha256} className="border-t border-outline-variant align-top">
                  <td className="py-space-xs pr-space-sm text-on-surface">{file.name}</td>
                  <td className="py-space-xs pr-space-sm">
                    <input
                      aria-label={`Volume for ${file.name}`}
                      inputMode="decimal"
                      value={choice?.volume ?? file.volume ?? ''}
                      onChange={(event) => override(file, { volume: event.target.value || null })}
                      className="w-16 rounded-lg bg-surface-container-lowest px-3 py-2 text-body-sm text-on-surface focus:outline-hidden focus:ring-1 focus:ring-primary"
                    />
                  </td>
                  <td className="py-space-xs pr-space-sm">
                    <SegmentedControl
                      options={EDITIONS}
                      value={choice?.edition ?? file.edition}
                      onChange={(edition) => override(file, { edition })}
                    />
                  </td>
                  <td className="py-space-xs pr-space-sm text-on-surface-variant">{readAs(file)}</td>
                  <td className="py-space-xs pr-space-sm font-mono text-label-sm text-on-surface-variant">
                    {becomes(file)}
                  </td>
                  <td className="py-space-xs">
                    <div className="flex flex-col items-start gap-space-xs">
                      {statusBadge(file, Boolean(choice?.replace))}
                      {file.status === 'exists' && (
                        <label className="inline-flex items-center gap-space-xs text-label-sm text-on-surface-variant">
                          <input
                            type="checkbox"
                            checked={Boolean(choice?.replace)}
                            onChange={(event) => override(file, { replace: event.target.checked })}
                          />
                          Replace
                        </label>
                      )}
                      {file.reason && file.status !== 'exists' && (
                        <span className="text-label-sm text-on-surface-variant">{file.reason}</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-label-sm text-on-surface-variant">
          Edits to volume or edition are checked again when you import.
        </p>
        <div className="flex flex-wrap items-center gap-space-sm">
          <Button variant="primary" disabled={importable === 0} onClick={() => void confirm(preview)}>
            Import {importable} files
          </Button>
          <Button variant="ghost" onClick={() => setStage({ step: 'idle' })}>
            Cancel
          </Button>
        </div>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-space-sm">
      {notice}
      <button
        type="button"
        onClick={() => picker.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={stage.step === 'reading'}
        className={
          dragging
            ? 'flex flex-col items-center gap-space-xs rounded-xl border border-dashed border-primary bg-primary/[0.12] px-space-md py-space-lg text-body-sm text-on-surface'
            : 'flex flex-col items-center gap-space-xs rounded-xl border border-dashed border-outline-variant bg-surface-container px-space-md py-space-lg text-body-sm text-on-surface-variant'
        }
      >
        <Icon name="book" className="h-5 w-5" />
        {stage.step === 'reading' ? 'Reading files…' : 'Drop PDFs or EPUBs here, or click to choose'}
      </button>
      <input
        ref={picker}
        type="file"
        accept=".pdf,.epub,application/pdf,application/epub+zip"
        multiple
        hidden
        onChange={(event) => {
          void read(Array.from(event.target.files ?? []))
          event.target.value = ''
        }}
      />
      <p className="text-label-sm text-on-surface-variant">
        Nothing is written until you review the files and press Import. Importing never marks a chapter read.
      </p>
    </section>
  )
}
