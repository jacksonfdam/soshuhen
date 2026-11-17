// What is said for a page, and nothing about how it is said. Kept free of
// imports that are not types so `node --test` can run it as it is.

import type { NarrationDirection, PageTranscript, ReaderMode } from '../../../lib/api'

/** One thing the narrator says, and what on the page it is: the page itself
    (no panel), a panel's announcement (no block), or a block of lettering. */
export interface ScriptItem {
  text: string
  /** Zero-based, as the reader counts pages. Spoken as one more. */
  page: number
  panel: number | null
  block: number | null
}

export const UNREADABLE = 'This page could not be read aloud.'
export const CHAPTER_END = 'End of chapter.'
const NO_TEXT = 'No text.'

/** Only the mode drawn right to left is read that way; the others are drawn
    left to right or top to bottom, and read as they are drawn. */
export function narrationDirection(mode: ReaderMode): NarrationDirection {
  return mode === 'paged_rtl' ? 'rtl' : 'ltr'
}

export function pageScript(page: number, transcript: PageTranscript): ScriptItem[] {
  const items: ScriptItem[] = [{ text: `Page ${page + 1}.`, page, panel: null, block: null }]

  const spoken = transcript.panels.map((panel) =>
    panel.blocks
      .map((block, index) => ({ text: block.text.trim(), index }))
      .filter((block) => block.text !== ''),
  )
  // One sentence for a page nobody speaks on, however many panels it has: a
  // listener told "Panel 1. No text. Panel 2. No text." has learnt nothing more.
  if (spoken.every((blocks) => blocks.length === 0)) {
    items.push({ text: NO_TEXT, page, panel: null, block: null })
    return items
  }

  // A page that is one panel is not announced as one. Every page of a long
  // strip is, and "Panel 1" before each would be noise.
  const announce = transcript.panels.length > 1
  spoken.forEach((blocks, panel) => {
    if (announce) items.push({ text: `Panel ${panel + 1}.`, page, panel, block: null })
    if (blocks.length === 0) {
      items.push({ text: NO_TEXT, page, panel, block: null })
      return
    }
    for (const block of blocks) items.push({ text: block.text, page, panel, block: block.index })
  })
  return items
}

export function failureScript(page: number): ScriptItem[] {
  return [
    { text: `Page ${page + 1}.`, page, panel: null, block: null },
    { text: UNREADABLE, page, panel: null, block: null },
  ]
}
