import { useCallback, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api, ApiError } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { ReaderMessage } from '../../ui/ReaderMessage'

/** Continue reading: the server knows where, this only goes there. */
export function ResumePage() {
  const seriesId = Number(useParams().seriesId)
  const navigate = useNavigate()
  // A novel resumes through its own route: the comic one only ever answers a
  // chapter, because the Android app decodes that shape, and would send a
  // novel's chapter to the image reader. Asked first because only it can tell
  // a novel apart; for a comic it answers 404 and the comic route decides.
  const load = useCallback(
    () =>
      api.proseResume(seriesId).then(
        (prose) => `/read/prose/${prose.kind}/${prose.id}`,
        async (failure: unknown) => {
          if (!(failure instanceof ApiError) || failure.status !== 404) throw failure
          const comic = await api.readerResume(seriesId)
          return `/read/${comic.chapter_id}?page=${comic.page}`
        },
      ),
    [seriesId],
  )
  const { data, error, notFound } = useAsyncData(load)
  const back = `/series/${seriesId}`

  useEffect(() => {
    if (data) navigate(data, { replace: true })
  }, [data, navigate])

  if (notFound) {
    return (
      <ReaderMessage
        title="Nothing to read yet"
        detail="No chapters of this series have been found at its source."
        backTo={back}
      />
    )
  }
  if (error) return <ReaderMessage title="Could not open the reader" detail={error} backTo={back} />
  return <ReaderMessage title="Opening…" backTo={back} />
}
