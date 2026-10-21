package app.soshuhen.reader

import app.soshuhen.api.SoshuhenApi
import okio.Path

/** Where a chapter's pages come from: files extracted on the device, or the server. */
sealed interface PageSource {
    data class Device(val pages: List<Path>) : PageSource

    data class Server(val api: SoshuhenApi, val chapterId: Long, val pageCount: Int) : PageSource
}
