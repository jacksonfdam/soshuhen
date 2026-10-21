package app.soshuhen.detail

import app.soshuhen.api.Resume
import app.soshuhen.api.SeriesDetail
import kotlin.math.floor

/** Where a chapter can be read from. Part 3 adds the device itself. */
enum class Availability { OnServer, NotDownloaded }

data class ChapterRow(
    val id: Long,
    val number: Double,
    val title: String?,
    val read: Boolean,
    val availability: Availability,
)

fun chapterRows(detail: SeriesDetail): List<ChapterRow> = detail.chapters
    .sortedByDescending { it.number }
    .map {
        ChapterRow(
            id = it.id,
            number = it.number,
            title = it.title,
            // Lists count whole chapters, as the server's complete route does:
            // 2.5 is read once chapter 2 is.
            read = floor(it.number) <= detail.series.progress,
            availability = if (it.state == "downloaded" && it.filePath != null) {
                Availability.OnServer
            } else {
                Availability.NotDownloaded
            },
        )
    }

fun continueChapter(detail: SeriesDetail, resume: Resume?): ChapterRow? {
    val rows = chapterRows(detail)
    resume?.let { saved -> rows.firstOrNull { it.id == saved.chapterId }?.let { return it } }
    return rows.filter { !it.read && it.availability == Availability.OnServer }.minByOrNull { it.number }
}
