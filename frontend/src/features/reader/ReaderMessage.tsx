import { Link } from 'react-router-dom'

import { buttonClass } from '../../ui'

/** Every state the reader shows before it has a page to show. */
export function ReaderMessage({
  title,
  detail,
  backTo,
}: {
  title: string
  detail?: string
  backTo: string
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-space-md bg-reader-black px-space-lg text-center">
      <h1 className="text-headline-sm text-on-surface">{title}</h1>
      {detail && <p className="max-w-md text-body-md text-on-surface-variant">{detail}</p>}
      <Link to={backTo} className={buttonClass({ variant: 'surface' })}>
        Back
      </Link>
    </main>
  )
}
