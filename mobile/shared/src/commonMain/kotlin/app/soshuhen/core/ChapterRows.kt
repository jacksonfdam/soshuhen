package app.soshuhen.core

import app.soshuhen.api.SeriesDetail
import kotlin.math.floor

// Shared by the series screen and the reader, which must agree on what can be
// read from where.

/** Where a chapter can be read from. */
enum class Availability { OnDevice, OnServer, NotDownloaded }

data class ChapterRow(
    val id: Long,
    val number: Double,
    val title: String?,
    val read: Boolean,
    val availability: Availability,
)

fun chapterRows(detail: SeriesDetail, onDevice: Set<Long> = emptySet()): List<ChapterRow> = detail.chapters
    .sortedByDescending { it.number }
    .map {
        ChapterRow(
            id = it.id,
            number = it.number,
            title = it.title,
            // Lists count whole chapters, as the server's complete route does:
            // 2.5 is read once chapter 2 is.
            read = floor(it.number) <= detail.series.progress,
            // A copy on the device is what reading will use, whatever the server says.
            availability = if (it.id in onDevice) {
                Availability.OnDevice
            } else if (it.state == "downloaded" && it.filePath != null) {
                Availability.OnServer
            } else {
                Availability.NotDownloaded
            },
        )
    }
