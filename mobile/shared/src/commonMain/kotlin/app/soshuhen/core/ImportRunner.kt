package app.soshuhen.core

import app.soshuhen.api.ApiException
import app.soshuhen.api.SeriesChapter
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.db.ImportLogEntity
import io.ktor.utils.io.ByteReadChannel
import io.ktor.utils.io.readAvailable
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okio.Buffer
import okio.Sink
import kotlin.time.Duration
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Instant

/**
 * [imported]: chapter numbers copied this run, per series. [pending]: importable
 * chapters still missing from the device. [problem]: why the run stopped, if it did.
 */
data class ImportReport(
    val imported: Map<Long, List<Double>>,
    val seriesTitles: Map<Long, String>,
    val pending: Int,
    val problem: String?,
)

private const val FOLDER_GONE = "SD card or folder not available: pick the folder again in Settings"
private const val DEVICE_FULL = "Device full: free some space or delete read chapters"
private const val UNREADABLE = "Some chapters on the server could not be read; they will be tried again later"
private const val LOST_SERVER = "Lost the server while copying; will continue next time"

// Past this, the archives are broken on the server, not in transit, and
// fetching the rest would only waste the run.
private const val MAX_UNREADABLE = 3

private const val PART = ".part"

/** The body stopped before the archive's length: the server or the Wi-Fi went away. */
private class Interrupted(cause: Throwable? = null) : Exception(cause)

private class Stop(val problem: String) : Exception(problem)

private enum class Outcome { Copied, UpToDate, Adopted, Missing }

private class Work(val detail: SeriesDetail, val chapter: SeriesChapter, val indexed: DeviceChapter?) {
    val slug get() = detail.series.slug
    val fileName = chapter.filePath!!.substringAfterLast('/')
    val part = fileName + PART
    var outcome: Outcome? = null
}

private class Probe(val etag: String?, val total: Long?)

/**
 * Copies the chapters of marked series from the server into the picked folder.
 * Only ever deletes a `.part` it wrote itself; a finished file it did not index
 * is left alone, whoever put it there.
 */
class ImportRunner(
    private val session: Session,
    private val store: LocalStore,
    private val folder: ChapterFolder,
    private val outbox: Outbox,
    private val check: ArchiveCheck,
    private val clock: () -> Instant,
) {
    // The hourly worker and a run-now request are separate unique works, so
    // nothing in WorkManager stops them overlapping; two runs planning the same
    // chapters would write the same file at once.
    private val running = Mutex()

    suspend fun run(
        budget: Duration = 45.minutes,
        // Told once the plan is known and before the first copy: the worker decides
        // from it whether the run is long enough to deserve a foreground notification.
        onPlan: (missing: Int) -> Unit = {},
        onProgress: (done: Int, total: Int) -> Unit = { _, _ -> },
    ): ImportReport = running.withLock { runLocked(budget, onPlan, onProgress) }

    private suspend fun runLocked(
        budget: Duration,
        onPlan: (missing: Int) -> Unit,
        onProgress: (done: Int, total: Int) -> Unit,
    ): ImportReport {
        session.refreshLocation()
        val api = session.api.value
        if (!session.atHome.value || api == null) return ImportReport(emptyMap(), emptyMap(), pending = 0, problem = null)
        val started = clock()
        // Reading done on the train goes home first: it is small, and the
        // copies after it can take the rest of the run.
        outbox.drain(api)

        val work = mutableListOf<Work>()
        val imported = linkedMapOf<Long, MutableList<Double>>()
        val titles = linkedMapOf<Long, String>()
        var unreadable = 0

        suspend fun copy(w: Work): Outcome {
            val namedAsIndexed = w.indexed != null && w.indexed.fileName == w.fileName
            if (w.indexed != null) {
                val current = probe(api, w.chapter.id, w.indexed.size)
                if (current != null && current.etag == w.indexed.etag) return Outcome.UpToDate
            }
            if (!namedAsIndexed) {
                // A rename onto this name would replace it, and the app never
                // removes a file it did not make.
                folder.size(w.slug, w.fileName)?.let { existing -> return adopt(api, w, existing) }
            }
            // Known to be missing from here on, should the run stop mid-copy.
            w.outcome = Outcome.Missing
            val got = try {
                download(api, w)
            } catch (e: DeviceFull) {
                // Whatever fitted is useless, and it holds the space the user needs back.
                removePart(w)
                throw e
            }
            val partUri = folder.find(w.slug, w.part) ?: return Outcome.Missing
            if (!passes(partUri)) {
                removePart(w)
                unreadable++
                if (unreadable >= MAX_UNREADABLE) throw Stop(UNREADABLE)
                return Outcome.Missing
            }
            val size = folder.size(w.slug, w.part) ?: return Outcome.Missing
            val uri = folder.rename(w.slug, w.part, w.fileName)
            store.forgetPart(w.chapter.id)
            val now = clock()
            store.indexChapter(
                DeviceChapter(w.chapter.id, w.detail.series.id, w.chapter.number, w.fileName, uri, got.etag, size, now),
            )
            store.logImport(
                ImportLogEntity(w.chapter.id, w.detail.series.id, w.detail.series.title, w.chapter.number, now.toEpochMilliseconds()),
            )
            imported.getOrPut(w.detail.series.id) { mutableListOf() } += w.chapter.number
            titles[w.detail.series.id] = w.detail.series.title
            return Outcome.Copied
        }

        suspend fun copyOne(w: Work): Outcome = try {
            copy(w)
        } catch (e: ApiException) {
            // The library lost this one archive although the chapter says
            // downloaded; stopping here would stop every run at the same place.
            if (e.status != 404) throw e
            if (w.indexed != null) Outcome.UpToDate else Outcome.Missing
        } catch (_: ChapterFileMissing) {
            // A file removed by hand mid-run is that chapter's loss alone; a
            // folder that went with it is everyone's.
            if (!folder.isAvailable()) throw FolderUnavailable()
            Outcome.Missing
        }

        val problem = try {
            store.saveSeries(api.seriesJson())
            for (id in store.markedIds().first()) {
                val json = try {
                    api.seriesDetailJson(id)
                } catch (e: ApiException) {
                    // Removed from the server: nothing to copy, and the rest still is.
                    if (e.status == 404) continue else throw e
                }
                store.saveDetail(id, json)
                val detail = SoshuhenJson.decodeFromString<SeriesDetail>(json)
                if (detail.series.kind == "prose") continue
                detail.chapters
                    .filter { it.state == "downloaded" && it.filePath != null }
                    // Oldest first, so a series is readable from its start while the rest copies.
                    .sortedBy { it.number }
                    .forEach { work += Work(detail, it, store.deviceChapter(it.id)) }
            }
            onPlan(work.count { it.indexed == null })
            onProgress(0, work.size)
            for ((done, w) in work.withIndex()) {
                // The next periodic run continues; one run must not eat the day's dataSync time.
                if (clock() - started >= budget) break
                w.outcome = copyOne(w)
                onProgress(done + 1, work.size)
            }
            null
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            problemFor(e) ?: throw e
        }
        store.setProblem(problem)

        // A chapter already on the device that was never reached is not known to be stale.
        val pending = work.count { it.outcome == Outcome.Missing || (it.outcome == null && it.indexed == null) }
        return ImportReport(imported, titles, pending, problem)
    }

    private fun problemFor(e: Exception): String? = when {
        e is FolderUnavailable -> FOLDER_GONE
        e is DeviceFull -> DEVICE_FULL
        e is Stop -> e.problem
        e is ApiException || e is Interrupted -> LOST_SERVER
        // A pulled card fails as a missing file or a bare IOException, never
        // as FolderUnavailable; once the folder is gone, only picking it again helps.
        !folder.isAvailable() -> FOLDER_GONE
        e is kotlinx.io.IOException || e is okio.IOException -> LOST_SERVER
        else -> null
    }

    /**
     * The archive's ETag and length from its last byte, so a chapter that has
     * not changed costs one byte instead of the whole file. Null when the
     * archive is now shorter than [size], which is a change too.
     */
    private suspend fun probe(api: SoshuhenApi, chapterId: Long, size: Long): Probe? = try {
        api.archive(chapterId, from = (size - 1).coerceAtLeast(0)) { Probe(it.etag, it.total) }
    } catch (e: ApiException) {
        if (e.status == 416) null else throw e
    }

    // Kept only when it is byte for byte the server's archive and readable: a
    // folder restored after a reinstall should not be copied a second time.
    private suspend fun adopt(api: SoshuhenApi, w: Work, existing: Long): Outcome {
        val current = probe(api, w.chapter.id, existing) ?: return Outcome.Missing
        if (current.total != existing) return Outcome.Missing
        val uri = folder.find(w.slug, w.fileName) ?: return Outcome.Missing
        if (!passes(uri)) return Outcome.Missing
        store.indexChapter(
            DeviceChapter(w.chapter.id, w.detail.series.id, w.chapter.number, w.fileName, uri, current.etag, existing, clock()),
        )
        return Outcome.Adopted
    }

    private suspend fun download(api: SoshuhenApi, w: Work): Probe {
        val held = folder.size(w.slug, w.part) ?: 0L
        val startedFrom = if (held > 0) store.partEtag(w.chapter.id) else null
        // A .part with no recorded ETag cannot be vouched for as the head of
        // the current archive, so it is written over from the start.
        val from = if (startedFrom == null) 0L else held
        return try {
            fetch(api, w, from, startedFrom)
        } catch (e: ApiException) {
            if (e.status != 416 || from == 0L) throw e
            // Asking past the end of a .part that is already whole is refused;
            // its length and ETag decide whether it is the archive or a
            // leftover of an older, longer one.
            val current = probe(api, w.chapter.id, from)
            if (current != null && current.total == from && current.etag == startedFrom) return current
            removePart(w)
            fetch(api, w, 0L, null)
        }
    }

    private suspend fun fetch(api: SoshuhenApi, w: Work, from: Long, ifRange: String?): Probe {
        val got = api.archive(w.chapter.id, from, ifRange) { d ->
            val append = from > 0 && !d.restarted
            if (!append) {
                // Recorded before the first byte, so a copy cut off at any point resumes only onto its own archive.
                d.etag?.let { store.savePartEtag(w.chapter.id, it) } ?: store.forgetPart(w.chapter.id)
            }
            folder.write(w.slug, w.part, append) { sink -> pump(d.body, sink) }
            Probe(d.etag, d.total)
        }
        // A connection that closes cleanly mid-body looks like the end of the file.
        if (got.total != null && folder.size(w.slug, w.part) != got.total) throw Interrupted()
        return got
    }

    private suspend fun pump(body: ByteReadChannel, sink: Sink) {
        val bytes = ByteArray(64 * 1024)
        val buffer = Buffer()
        while (true) {
            // Tagged here so a failing read from the server is told apart from a
            // failing write to the folder, which share this block.
            val n = try {
                body.readAvailable(bytes, 0, bytes.size)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                throw Interrupted(e)
            }
            if (n == -1) break
            buffer.write(bytes, 0, n)
            sink.write(buffer, n.toLong())
        }
    }

    private suspend fun passes(uri: String): Boolean {
        val source = folder.read(uri)
        return try {
            check.pageCount(source) > 0
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            false
        } finally {
            source.close()
        }
    }

    private suspend fun removePart(w: Work) {
        store.forgetPart(w.chapter.id)
        try {
            folder.find(w.slug, w.part)?.let { folder.delete(it) }
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            // Best effort: the problem being reported matters more than the leftover.
        }
    }
}
