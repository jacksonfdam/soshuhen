package app.soshuhen.core

import app.soshuhen.api.ApiException
import app.soshuhen.api.ReaderPrefs
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.db.OutboxEntity
import kotlinx.coroutines.CancellationException
import kotlin.time.Instant

data class DrainResult(val sent: Int, val dropped: Int, val remaining: Int)

/**
 * Reading done away from home, kept to tell the server in order once the
 * phone is back on the home network.
 */
class Outbox(private val store: LocalStore, private val clock: () -> Instant) {

    // Only the latest position matters, so an earlier one is replaced instead
    // of replayed page by page.
    suspend fun position(seriesId: Long, chapterId: Long, page: Int) {
        store.dropQueued(seriesId, POSITION)
        store.enqueue(
            OutboxEntity(
                kind = POSITION, seriesId = seriesId, chapterId = chapterId, page = page,
                readAt = clock().toString(), body = null,
            ),
        )
    }

    // Appended, never replaced: each finished chapter moves list progress.
    suspend fun complete(seriesId: Long, chapterId: Long) {
        store.enqueue(
            OutboxEntity(
                kind = COMPLETE, seriesId = seriesId, chapterId = chapterId, page = null,
                readAt = clock().toString(), body = null,
            ),
        )
    }

    suspend fun prefs(seriesId: Long, prefs: ReaderPrefs) {
        store.dropQueued(seriesId, PREFS)
        store.enqueue(
            OutboxEntity(
                kind = PREFS, seriesId = seriesId, chapterId = null, page = null, readAt = null,
                body = SoshuhenJson.encodeToString(ReaderPrefs.serializer(), prefs),
            ),
        )
    }

    suspend fun drain(api: SoshuhenApi): DrainResult {
        var sent = 0
        var dropped = 0
        val queued = store.outbox()
        for ((index, event) in queued.withIndex()) {
            try {
                send(api, event)
                sent++
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                // The server understood and said no for good (a chapter that
                // no longer exists); retrying would block everything behind it.
                if (!isPermanent(e.status)) return DrainResult(sent, dropped, queued.size - index)
                dropped++
            } catch (_: Exception) {
                // 5xx, timeout, no route: everything from here on stays, in order.
                return DrainResult(sent, dropped, queued.size - index)
            }
            store.dequeue(event.id)
        }
        return DrainResult(sent, dropped, remaining = 0)
    }

    private fun isPermanent(status: Int) = status in 400..499 && status != 408 && status != 429

    private suspend fun send(api: SoshuhenApi, e: OutboxEntity) {
        when (e.kind) {
            POSITION -> api.putPosition(e.seriesId, e.chapterId!!, e.page!!, Instant.parse(e.readAt!!))
            COMPLETE -> api.complete(e.chapterId!!, Instant.parse(e.readAt!!))
            PREFS -> api.putPrefs(e.seriesId, SoshuhenJson.decodeFromString(ReaderPrefs.serializer(), e.body!!))
        }
    }

    private companion object {
        const val POSITION = "position"
        const val COMPLETE = "complete"
        const val PREFS = "prefs"
    }
}
