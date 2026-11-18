// Whether a key pressed in the reader belongs to the control that has focus.
// No imports, so `node --test` can run it as it is.

/**
 * True when the focused control uses this key itself, and the reader's own
 * shortcut for it must not also fire.
 *
 * The reader listens on the window, so without this a key does two things at
 * once. The space bar on the read-aloud bar's Pause button paused and turned
 * the page; a letter typed to find a voice in its list turned narration off.
 * Keys a control has no use for still reach the reader: the arrows turn pages
 * from a focused button, which is where focus is left after any click.
 */
export function keptByControl(tag: string, type: string | null, key: string): boolean {
  switch (tag) {
    case 'TEXTAREA':
    case 'SELECT':
      return true
    case 'INPUT':
      // The page slider is the exception: it is the reader's own control, and
      // the arrows turning pages from it is what moves it.
      return type !== 'range'
    case 'BUTTON':
      return key === ' ' || key === 'Enter'
    case 'A':
      return key === 'Enter'
    default:
      return false
  }
}
