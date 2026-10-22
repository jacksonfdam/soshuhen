package app.soshuhen.core

import app.soshuhen.api.Series
import app.soshuhen.api.SeriesDetail
import kotlinx.coroutines.flow.first
import kotlin.math.floor

/**
 * What the user chose to keep on the device. Every deletion here answers a
 * request for it: unmarking alone never touches a file.
 */
class DeviceLibrary(private val store: LocalStore, private val folder: ChapterFolder) {
    suspend fun mark(series: Series) = store.mark(series.id, series.slug)

    suspend fun unmark(seriesId: Long, deleteFiles: Boolean) {
        // Files first: if the folder is unavailable the series stays marked and
        // indexed, so the user sees the failure instead of orphaned files.
        if (deleteFiles) store.deviceChapters(seriesId).first().forEach { remove(it) }
        store.unmark(seriesId)
    }

    suspend fun deleteChapter(chapterId: Long) {
        store.deviceChapter(chapterId)?.let { remove(it) }
    }

    /** Chapters count whole, as everywhere: 2.5 is read once chapter 2 is. */
    suspend fun deleteRead(detail: SeriesDetail) {
        store.deviceChapters(detail.series.id).first()
            .filter { floor(it.number) <= detail.series.progress }
            .forEach { remove(it) }
    }

    private suspend fun remove(chapter: DeviceChapter) {
        // A file the user already removed by hand is the state we wanted; the
        // index entry would otherwise claim a chapter that cannot be opened.
        try {
            folder.delete(chapter.uri)
        } catch (_: ChapterFileMissing) {
        }
        store.forgetChapter(chapter.chapterId)
    }
}
