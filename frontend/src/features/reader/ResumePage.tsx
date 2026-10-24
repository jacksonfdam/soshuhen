import { useCallback, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { ReaderMessage } from '../../ui/ReaderMessage'

/** Continue reading: the server knows where, this only goes there. */
export function ResumePage() {
  const seriesId = Number(useParams().seriesId)
  const navigate = useNavigate()
  const load = useCallback(() => api.readerResume(seriesId), [seriesId])
  const { data, error, notFound } = useAsyncData(load)
  const back = `/series/${seriesId}`

  useEffect(() => {
    if (data) navigate(`/read/${data.chapter_id}?page=${data.page}`, { replace: true })
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
