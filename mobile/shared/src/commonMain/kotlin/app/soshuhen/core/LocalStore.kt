package app.soshuhen.core

import androidx.room.immediateTransaction
import androidx.room.useWriterConnection
import app.soshuhen.api.ReaderPrefs
import app.soshuhen.api.Resume
import app.soshuhen.api.Series
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.db.DeviceChapterEntity
import app.soshuhen.db.DeviceVolumeEntity
import app.soshuhen.db.ImportLogEntity
import app.soshuhen.db.ImportPartEntity
import app.soshuhen.db.MarkedEntity
import app.soshuhen.db.OutboxEntity
import app.soshuhen.db.ProblemEntity
import app.soshuhen.db.SnapshotEntity
import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.serialization.builtins.nullable
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import kotlin.time.Clock
import kotlin.time.Instant

data class DeviceChapter(
    val chapterId: Long,
    val seriesId: Long,
    val number: Double,
    val fileName: String,
    val uri: String,
    val etag: String?,
    val size: Long,
    val importedAt: Instant,
)

data class DeviceVolume(
    val volumeId: Long,
    val seriesId: Long,
    val number: Double,
    val fileName: String,
    val uri: String,
    val etag: String?,
    val size: Long,
    val importedAt: Instant,
)

private const val SERIES_KEY = "series"
private const val INSTANCE_KEY = "instance"

// Unquoted, so never equal to an ETag a server sends.
private const val UNREADABLE_ETAG = "unreadable"
private fun detailKey(id: Long) = "series/$id"
private fun prefsKey(id: Long) = "prefs/$id"
private fun resumeKey(id: Long) = "resume/$id"
private fun volumesKey(id: Long) = "volumes/$id"

/**
 * The screens and the importer speak the API's types, not Room's rows, so a
 * change in how something is stored stays in this file.
 */
// Open so a test can hand a view model a store whose writes fail: a closed Room
// database hangs instead of throwing, which proves nothing about the fallback.
open class LocalStore(
    private val db: SoshuhenDatabase,
    private val clock: () -> Instant = { Clock.System.now() },
) {
    open suspend fun saveSeries(json: String) = save(SERIES_KEY, json)

    suspend fun seriesSnapshot(): List<Series>? = read(SERIES_KEY)

    open suspend fun saveDetail(id: Long, json: String) = save(detailKey(id), json)

    suspend fun detailSnapshot(id: Long): SeriesDetail? = read(detailKey(id))

    suspend fun savePrefs(seriesId: Long, prefs: ReaderPrefs) =
        save(prefsKey(seriesId), SoshuhenJson.encodeToString(ReaderPrefs.serializer(), prefs))

    suspend fun prefsSnapshot(seriesId: Long): ReaderPrefs? = read(prefsKey(seriesId))

    // Saved when the server has no place too: an older place must not outlive
    // the server saying there is none.
    suspend fun saveResume(seriesId: Long, resume: Resume?) =
        save(resumeKey(seriesId), SoshuhenJson.encodeToString(Resume.serializer().nullable, resume))

    /**
     * A page turned away from home and not yet told to the server: newer than
     * anything the server said, so it wins wherever the two disagree.
     */
    suspend fun queuedPosition(seriesId: Long): Resume? =
        db.outbox().all().lastOrNull { it.seriesId == seriesId && it.kind == Outbox.POSITION }
            ?.let { queued -> Resume(queued.chapterId ?: return null, queued.page ?: return null) }

    /** Where reading of a series stopped, as far as the device knows without the server. */
    suspend fun resume(seriesId: Long): Resume? = queuedPosition(seriesId) ?: read<Resume?>(resumeKey(seriesId))

    /**
     * A chapter finished away from home shows as read in the library and on the
     * series at once, rather than after the next sync. Never lowers: the server
     * only ever moves progress forward, and so does this.
     */
    suspend fun raiseProgress(seriesId: Long, progress: Int) {
        rewrite(SERIES_KEY) { root ->
            if (root !is JsonArray) return@rewrite root
            JsonArray(root.map { if (isSeries(it, seriesId)) raised(it as JsonObject, progress) else it })
        }
        rewrite(detailKey(seriesId)) { root ->
            val series = (root as? JsonObject)?.get("series") as? JsonObject ?: return@rewrite root
            JsonObject(root + ("series" to raised(series, progress)))
        }
    }

    // Edited as JSON rather than through the models, which would drop every
    // field the app does not read and leave a snapshot that is no longer what
    // the server said.
    private suspend fun rewrite(key: String, change: (JsonElement) -> JsonElement) {
        val json = db.snapshots().get(key)?.json ?: return
        val root = try {
            SoshuhenJson.parseToJsonElement(json)
        } catch (_: kotlinx.serialization.SerializationException) {
            return
        }
        val changed = change(root)
        if (changed != root) save(key, SoshuhenJson.encodeToString(JsonElement.serializer(), changed))
    }

    private fun isSeries(element: JsonElement, id: Long) =
        ((element as? JsonObject)?.get("id") as? JsonPrimitive)?.longOrNull == id

    private fun raised(series: JsonObject, progress: Int): JsonObject {
        val current = (series["progress"] as? JsonPrimitive)?.intOrNull ?: 0
        return if (progress > current) JsonObject(series + ("progress" to JsonPrimitive(progress))) else series
    }

    /**
     * The highest light novel volume finished on this device. The lists' own
     * count arrives with the detail; this covers what they have not heard yet.
     * Never lowers, as chapter progress never does.
     */
    suspend fun raiseVolumeProgress(seriesId: Long, number: Int) {
        if (number > (volumeProgress(seriesId) ?: 0)) {
            save(volumesKey(seriesId), SoshuhenJson.encodeToString(Int.serializer(), number))
        }
    }

    suspend fun volumeProgress(seriesId: Long): Int? = read(volumesKey(seriesId))

    // For a feature's own small state (the prose reader's places and type),
    // kept beside the snapshots so a switch of server clears it with them.
    suspend fun putValue(key: String, json: String) = save(key, json)

    suspend fun value(key: String): String? = db.snapshots().get(key)?.json

    fun isMarked(seriesId: Long): Flow<Boolean> = db.marked().isMarked(seriesId)

    fun markedIds(): Flow<Set<Long>> = db.marked().ids().map { it.toSet() }

    suspend fun mark(seriesId: Long, slug: String) =
        db.marked().put(MarkedEntity(seriesId, slug, clock().toEpochMilliseconds()))

    // Only the mark: the chapters already on the device stay, because the app
    // never deletes what the user did not ask it to.
    suspend fun unmark(seriesId: Long) = db.marked().delete(seriesId)

    fun deviceChapters(seriesId: Long): Flow<List<DeviceChapter>> =
        db.deviceChapters().forSeries(seriesId).map { rows -> rows.map { it.toChapter() } }

    suspend fun deviceChapter(chapterId: Long): DeviceChapter? = db.deviceChapters().get(chapterId)?.toChapter()

    fun allDeviceChapterIds(): Flow<Set<Long>> = db.deviceChapters().ids().map { it.toSet() }

    /** Every series with at least one chapter or volume copied to the device. */
    fun seriesWithChapters(): Flow<Set<Long>> =
        combine(db.deviceChapters().seriesIds(), db.deviceVolumes().seriesIds()) { a, b -> (a + b).toSet() }

    suspend fun indexChapter(c: DeviceChapter) = db.deviceChapters().put(
        DeviceChapterEntity(
            c.chapterId, c.seriesId, c.number, c.fileName, c.uri, c.etag, c.size,
            c.importedAt.toEpochMilliseconds(),
        ),
    )

    suspend fun forgetChapter(chapterId: Long) = db.deviceChapters().delete(chapterId)

    /**
     * A copy the reader could not open stays indexed, but as matching no ETag
     * the server sends: the next import then copies the chapter over the app's
     * own file. Forgotten instead, the file would be one the app no longer
     * knows, which it never writes over, and the chapter would never come back.
     */
    suspend fun markUnreadable(chapterId: Long) = db.deviceChapters().setEtag(chapterId, UNREADABLE_ETAG)

    fun deviceVolumes(seriesId: Long): Flow<List<DeviceVolume>> =
        db.deviceVolumes().forSeries(seriesId).map { rows -> rows.map { it.toVolume() } }

    suspend fun deviceVolume(volumeId: Long): DeviceVolume? = db.deviceVolumes().get(volumeId)?.toVolume()

    suspend fun indexVolume(v: DeviceVolume) = db.deviceVolumes().put(
        DeviceVolumeEntity(
            v.volumeId, v.seriesId, v.number, v.fileName, v.uri, v.etag, v.size,
            v.importedAt.toEpochMilliseconds(),
        ),
    )

    suspend fun forgetVolume(volumeId: Long) = db.deviceVolumes().delete(volumeId)

    /** As [markUnreadable], for a volume. */
    suspend fun markVolumeUnreadable(volumeId: Long) = db.deviceVolumes().setEtag(volumeId, UNREADABLE_ETAG)

    fun problem(): Flow<String?> = db.problems().message()

    suspend fun setProblem(message: String?) {
        if (message == null) db.problems().clear()
        else db.problems().put(ProblemEntity(ProblemEntity.ONLY_ROW, message, at = clock().toEpochMilliseconds()))
    }

    open suspend fun enqueue(entry: OutboxEntity) = db.outbox().put(entry)

    suspend fun outbox(): List<OutboxEntity> = db.outbox().all()

    suspend fun dequeue(id: Long) = db.outbox().delete(id)

    suspend fun dropQueued(seriesId: Long, kind: String) = db.outbox().deleteKind(seriesId, kind)

    suspend fun logImport(entry: ImportLogEntity) = db.importLog().put(entry)

    fun importLog(): Flow<List<ImportLogEntity>> = db.importLog().newestFirst()

    suspend fun savePartEtag(ref: BookRef, etag: String) =
        db.importParts().put(ImportPartEntity(ref.id, etag, ref.kind.key))

    suspend fun partEtag(ref: BookRef): String? = db.importParts().etag(ref.kind.key, ref.id)

    suspend fun forgetPart(ref: BookRef) = db.importParts().delete(ref.kind.key, ref.id)

    /**
     * Every id kept here is one server installation's. When the saved server
     * turns out to be another installation, the queued reading, the marks, the
     * index and the snapshots would name its series by the old one's ids, and
     * replaying them would move unrelated list progress. The files in the folder
     * stay: they are the user's, and the new server's copies adopt them by name.
     * One transaction, so a process killed half-way leaves either the old
     * installation's data whole or none of it. Cleared piecemeal, the snapshots
     * (which hold the instance key) went before the marks, and a death between
     * them made the next save adopt the old server's marks as the new one's.
     */
    // A seam for the test that kills the switch half-way; nothing else sets it.
    internal var beforeRecordingInstance: suspend () -> Unit = {}

    suspend fun belongTo(instanceId: String) {
        db.useWriterConnection { connection ->
            connection.immediateTransaction {
                val current = read<String>(INSTANCE_KEY)
                if (current == instanceId) return@immediateTransaction
                // Nothing recorded is a device set up before this was kept: its
                // data was the saved server's, which is the one being saved again.
                if (current != null) {
                    db.outbox().clear()
                    db.importParts().clear()
                    db.problems().clear()
                    db.marked().clear()
                    db.deviceChapters().clear()
                    db.deviceVolumes().clear()
                    db.snapshots().clear()
                }
                beforeRecordingInstance()
                save(INSTANCE_KEY, SoshuhenJson.encodeToString(String.serializer(), instanceId))
            }
        }
    }

    private suspend fun save(key: String, json: String) =
        db.snapshots().put(SnapshotEntity(key, json, clock().toEpochMilliseconds()))

    // A snapshot the current models cannot read is no snapshot: the screen
    // falls back to its failure state rather than crashing on an old shape.
    private suspend inline fun <reified T> read(key: String): T? {
        val json = db.snapshots().get(key)?.json ?: return null
        return try {
            SoshuhenJson.decodeFromString<T>(json)
        } catch (_: kotlinx.serialization.SerializationException) {
            null
        }
    }

    private fun DeviceVolumeEntity.toVolume() = DeviceVolume(
        volumeId, seriesId, number, fileName, uri, etag, size, Instant.fromEpochMilliseconds(importedAt),
    )

    private fun DeviceChapterEntity.toChapter() = DeviceChapter(
        chapterId, seriesId, number, fileName, uri, etag, size, Instant.fromEpochMilliseconds(importedAt),
    )
}
