import type { PageTranscript } from '../../lib/api'
import { ReaderSheet } from '../../ui/ReaderSheet'
import { UNREADABLE, type ScriptItem } from './lib/narrationScript'

/**
 * What narration says about the pages on screen, as text.
 *
 * Ordinary headings and lists, and deliberately no live region: a screen
 * reader that announced each line as it was marked would talk over the voice
 * already reading it. A listener who wants the text, or a braille display,
 * reads it here at their own pace.
 */
export function TranscriptPanel({
  pages,
  transcripts,
  failed,
  place,
  onClose,
}: {
  pages: number[]
  transcripts: Map<number, PageTranscript> | null
  failed: number | null
  place: ScriptItem | null
  onClose: () => void
}) {
  return (
    <ReaderSheet title="Page transcript" onClose={onClose}>
      {pages.length === 0 && (
        <p className="text-body-md text-on-surface-variant">The chapter has ended.</p>
      )}
      {pages.map((page) => {
        const transcript = transcripts?.get(page)
        return (
          <section key={page} className="pb-space-md">
            <h3 className="pb-space-sm text-title-md text-on-surface">Page {page + 1}</h3>
            {transcript ? (
              <PageText page={page} transcript={transcript} place={place} />
            ) : (
              <p className="text-body-md text-on-surface-variant">
                {failed === page ? UNREADABLE : 'Not read yet. Start Read aloud to read this page.'}
              </p>
            )}
          </section>
        )
      })}
    </ReaderSheet>
  )
}

function PageText({
  page,
  transcript,
  place,
}: {
  page: number
  transcript: PageTranscript
  place: ScriptItem | null
}) {
  // As the narration does: a page that is one panel is not called one.
  const several = transcript.panels.length > 1
  if (transcript.panels.every((panel) => panel.blocks.length === 0)) {
    return <p className="text-body-md text-on-surface-variant">No text.</p>
  }
  return (
    <>
      {transcript.panels.map((panel, panelIndex) => (
        <div key={panelIndex} className="pb-space-sm">
          {several && (
            <h4 className="pb-space-xs text-label-md text-on-surface-variant">
              Panel {panelIndex + 1}
            </h4>
          )}
          {panel.blocks.length === 0 ? (
            <p className="text-body-md text-on-surface-variant">No text.</p>
          ) : (
            <ol className="flex flex-col gap-space-xs">
              {panel.blocks.map((block, blockIndex) => {
                const speaking =
                  place !== null &&
                  place.page === page &&
                  place.panel === panelIndex &&
                  place.block === blockIndex
                return (
                  <li
                    key={blockIndex}
                    aria-current={speaking ? 'true' : undefined}
                    className={`rounded-sm px-space-xs text-body-md text-on-surface ${
                      speaking ? 'bg-primary/20' : ''
                    }`}
                  >
                    {block.text}
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      ))}
    </>
  )
}
