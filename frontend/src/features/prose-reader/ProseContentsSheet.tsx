import { ReaderSheet } from '../../ui'

export function ProseContentsSheet({
  sections,
  current,
  onPick,
  onClose,
}: {
  sections: { index: number; title: string | null }[]
  current: number
  onPick: (index: number) => void
  onClose: () => void
}) {
  // An EPUB written per chapter has one untitled section; its table of
  // contents would be a single "Section 1" and says nothing.
  const titled = sections.filter((section) => section.title)
  return (
    <ReaderSheet title="Contents" onClose={onClose}>
      {titled.length === 0 ? (
        <p className="text-body-md text-on-surface-variant">This book has no table of contents.</p>
      ) : (
        <ul className="flex flex-col">
          {titled.map((section) => (
            <li key={section.index}>
              <button
                type="button"
                aria-current={section.index === current ? 'true' : undefined}
                onClick={() => onPick(section.index)}
                className={`w-full rounded-lg px-space-sm py-space-sm text-left text-body-md transition-colors hover:bg-surface-container-high ${
                  section.index === current ? 'text-primary' : 'text-on-surface'
                }`}
              >
                {section.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </ReaderSheet>
  )
}
