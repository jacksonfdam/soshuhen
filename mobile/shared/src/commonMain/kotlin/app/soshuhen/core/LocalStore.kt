package app.soshuhen.core

import app.soshuhen.api.Series
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.db.DeviceChapterEntity
import app.soshuhen.db.MarkedEntity
import app.soshuhen.db.ProblemEntity
import app.soshuhen.db.SnapshotEntity
import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
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

/** Everything the app keeps on the device, behind the types the screens already use. */
class LocalStore(
    private val db: SoshuhenDatabase,
    private val clock: () -> Instant = { Clock.System.now() },
) {
    suspend fun saveSeries(json: String) = save(SERIES_KEY, json)

    suspend fun seriesSnapshot(): List<Series>? = read(SERIES_KEY)

    suspend fun saveDetail(id: Long, json: String) = save(detailKey(id), json)

    suspend fun detailSnapshot(id: Long): SeriesDetail? = read(detailKey(id))

    fun isMarked(seriesId: Long): Flow<Boolean> = db.marked().isMarked(seriesId)

    fun markedIds(): Flow<Set<Long>> = db.marked().ids().map { it.toSet() }

    suspend fun mark(seriesId: Long, slug: String) =
        db.marked().put(MarkedEntity(seriesId, slug, clock().toEpochMilliseconds()))

    // Only the mark: the chapters already on the device stay, because the app
    // never deletes what the user did not ask it to.
    suspend fun unmark(seriesId: Long) = db.marked().delete(seriesId)

    fun deviceChapters(seriesId: Long): Flow<List<DeviceChapter>> =
        db.deviceChapters().forSeries(seriesId).map { rows -> rows.map { it.toChapter() } }

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
        else db.problems().put(ProblemEntity(message = message, at = clock().toEpochMilliseconds()))
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

    private fun DeviceChapterEntity.toChapter() = DeviceChapter(
        chapterId, seriesId, number, fileName, uri, etag, size, Instant.fromEpochMilliseconds(importedAt),
    )
}
