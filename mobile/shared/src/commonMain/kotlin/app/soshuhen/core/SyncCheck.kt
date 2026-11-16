package app.soshuhen.core

import app.soshuhen.api.OffloadItem
import app.soshuhen.api.OffloadRequest
import app.soshuhen.api.SeriesDetail

/** A file the device holds and can vouch for: indexed, still there, the size it was copied at, with an ETag. */
data class Held(val ref: BookRef, val etag: String, val size: Long)

data class Missing(val ref: BookRef, val reason: MissingReason)

enum class MissingReason { NotCopied, FileGone, SizeMismatch, NoEtag, Unreadable }

/**
 * What the device holds of what the server holds. Deleting from the server is
 * offered only when every item is [Held]: one unverified file is one the user
 * could lose.
 */
data class SyncReport(
    val seriesCount: Int,
    val held: List<Held>,
    val missing: List<Missing>,
    // Offloaded volumes J-Novel Club has revised since: news, never a download by itself.
    val revised: List<Long>,
    val problem: String? = null,
) {
    val allVerified: Boolean get() = problem == null && missing.isEmpty() && held.isNotEmpty()
    val bytes: Long get() = held.sumOf { it.size }
    val total: Int get() = held.size + missing.size

    fun offloadRequest() = OffloadRequest(
        chapters = held.filter { it.ref.kind == BookKind.Chapter }.map { OffloadItem(it.ref.id, it.etag, it.size) },
        volumes = held.filter { it.ref.kind == BookKind.Volume }.map { OffloadItem(it.ref.id, it.etag, it.size) },
    )
}

/** The index, plus each indexed file's size on disk now; null when the file is gone. */
data class DeviceState(
    val chapters: Map<Long, DeviceChapter>,
    val volumes: Map<Long, DeviceVolume>,
    val actualSize: Map<String, Long?>,
)

private class IndexedCopy(val uri: String, val etag: String?, val size: Long)

fun checkSync(details: List<SeriesDetail>, device: DeviceState): SyncReport {
    val held = mutableListOf<Held>()
    val missing = mutableListOf<Missing>()
    val revised = mutableListOf<Long>()

    fun check(ref: BookRef, indexed: IndexedCopy?) {
        val reason = when {
            indexed == null -> MissingReason.NotCopied
            device.actualSize[indexed.uri] == null -> MissingReason.FileGone
            device.actualSize[indexed.uri] != indexed.size -> MissingReason.SizeMismatch
            indexed.etag == null -> MissingReason.NoEtag
            indexed.etag == UNREADABLE_ETAG -> MissingReason.Unreadable
            else -> null
        }
        if (reason == null) held += Held(ref, indexed!!.etag!!, indexed.size) else missing += Missing(ref, reason)
    }

    for (detail in details) {
        // The same scope as the importer: what the server can hand over as a file.
        detail.chapters.filter { it.state == "downloaded" && it.filePath != null }.sortedBy { it.number }.forEach {
            check(BookRef(BookKind.Chapter, it.id), device.chapters[it.id]?.let { c -> IndexedCopy(c.uri, c.etag, c.size) })
        }
        detail.volumes.filter { it.edition == "light" && it.id != null }.sortedBy { it.number }.forEach {
            if (it.state == "offloaded" && it.revised) revised += it.id!!
            if (it.state == "downloaded" && it.readable && it.filePath != null) {
                check(BookRef(BookKind.Volume, it.id!!), device.volumes[it.id]?.let { v -> IndexedCopy(v.uri, v.etag, v.size) })
            }
        }
    }
    return SyncReport(details.size, held, missing, revised)
}
