package app.soshuhen.core

import app.soshuhen.api.ReaderPrefs
import app.soshuhen.api.Resume
import app.soshuhen.api.Series
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.db.DeviceChapterEntity
import app.soshuhen.db.ImportLogEntity
import app.soshuhen.db.ImportPartEntity
import app.soshuhen.db.MarkedEntity
import app.soshuhen.db.OutboxEntity
import app.soshuhen.db.ProblemEntity
import app.soshuhen.db.SnapshotEntity
import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.builtins.nullable
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

private const val SERIES_KEY = "series"
private fun detailKey(id: Long) = "series/$id"
private fun prefsKey(id: Long) = "prefs/$id"
private fun resumeKey(id: Long) = "resume/$id"

/** Everything the app keeps on the device, behind the types the screens already use. */
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

    suspend fun indexChapter(c: DeviceChapter) = db.deviceChapters().put(
        DeviceChapterEntity(
            c.chapterId, c.seriesId, c.number, c.fileName, c.uri, c.etag, c.size,
            c.importedAt.toEpochMilliseconds(),
        ),
    )

    suspend fun forgetChapter(chapterId: Long) = db.deviceChapters().delete(chapterId)

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

    suspend fun savePartEtag(chapterId: Long, etag: String) = db.importParts().put(ImportPartEntity(chapterId, etag))

    suspend fun partEtag(chapterId: Long): String? = db.importParts().etag(chapterId)

    suspend fun forgetPart(chapterId: Long) = db.importParts().delete(chapterId)

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

    private fun DeviceChapterEntity.toChapter() = DeviceChapter(
        chapterId, seriesId, number, fileName, uri, etag, size, Instant.fromEpochMilliseconds(importedAt),
    )
}
