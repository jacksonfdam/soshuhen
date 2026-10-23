import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, type Series } from '../lib/api'
import { Icon, type IconName } from '../ui'
import { useScrollLock } from '../ui/useScrollLock'

export interface Command {
  id: string
  label: string
  icon: IconName
  run: () => void
}

// Enough to find a series by a word of its title without the list scrolling.
const SERIES_SHOWN = 8

function matches(text: string, words: string[]): boolean {
  const haystack = text.toLowerCase()
  return words.every((word) => haystack.includes(word))
}

/**
 * Ctrl+K (⌘K on a Mac) from anywhere in the shell: jump to a screen, open a
 * series by a word of its title, or run one of the shell's own actions.
 *
 * The series are fetched when the palette opens rather than kept warm: the
 * list changes with every sync, and a palette that offers a removed series is
 * worse than one that takes a moment to fill.
 */
export function CommandPalette({ commands }: { commands: Command[] }) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((was) => !was)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return open ? <Palette commands={commands} onClose={() => setOpen(false)} /> : null
}

function Palette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [series, setSeries] = useState<Series[]>([])
  const [active, setActive] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  useScrollLock(true)

  useEffect(() => {
    input.current?.focus()
    // A failure leaves the screens and actions, which need nothing fetched.
    api.series().then(setSeries).catch(() => undefined)
  }, [])

  const items = useMemo<Command[]>(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
    const shown = commands.filter((command) => matches(command.label, words))
    if (words.length === 0) return shown
    const title = query.trim()
    // Last, because it is the one item that sends requests to every site.
    const searchSources: Command = {
      id: 'search-sources',
      label: `Search sources for “${title}”`,
      icon: 'search',
      run: () => navigate(`/search?q=${encodeURIComponent(title)}`),
    }
    const found = series
      .filter((entry) => matches(entry.title, words))
      .slice(0, SERIES_SHOWN)
      .map<Command>((entry) => ({
        id: `series-${entry.id}`,
        label: entry.title,
        icon: 'book',
        run: () => navigate(`/series/${entry.id}`),
      }))
    return [...shown, ...found, searchSources]
  }, [commands, series, query, navigate])

  useEffect(() => setActive(0), [query])

  function run(command: Command | undefined) {
    if (!command) return
    onClose()
    command.run()
  }

  function onKeyDown(event: ReactKeyboardEvent) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((index) => Math.min(index + 1, items.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      run(items[active])
    } else if (event.key === 'Escape') {
      onClose()
    }
  }

  return (
    <>
      <div
        aria-hidden
        onClick={onClose}
        className="fixed inset-0 z-[60] bg-surface-container-lowest/70 backdrop-blur-sm"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={onKeyDown}
        className="fixed left-1/2 top-24 z-[70] w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-xl bg-surface-container shadow-overlay"
      >
        <div className="flex items-center gap-space-sm border-b border-outline-variant px-space-md">
          <Icon name="search" className="h-5 w-5 text-on-surface-variant" />
          <input
            ref={input}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Go to a screen or a series"
            aria-label="Command"
            aria-controls="command-results"
            aria-activedescendant={items[active] ? `command-${items[active].id}` : undefined}
            className="h-12 min-w-0 flex-1 bg-transparent text-body-lg text-on-surface outline-none"
          />
          <kbd className="font-mono text-label-sm text-on-surface-variant">Esc</kbd>
        </div>
        <ul id="command-results" role="listbox" className="max-h-96 overflow-y-auto p-space-xs">
          {items.length === 0 ? (
            <li className="px-space-md py-space-sm text-body-sm text-on-surface-variant">
              Nothing matches.
            </li>
          ) : (
            items.map((item, index) => (
              <li
                key={item.id}
                id={`command-${item.id}`}
                role="option"
                aria-selected={index === active}
                onMouseEnter={() => setActive(index)}
                onClick={() => run(item)}
                className={`flex cursor-pointer items-center gap-space-sm rounded-lg px-space-md py-space-sm text-body-md ${
                  index === active ? 'bg-surface-container-high text-on-surface' : 'text-on-surface-variant'
                }`}
              >
                <Icon name={item.icon} className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </li>
            ))
          )}
        </ul>
      </div>
    </>
  )
}
