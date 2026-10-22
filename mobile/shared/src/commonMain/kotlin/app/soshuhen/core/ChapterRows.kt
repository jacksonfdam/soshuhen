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
    // The server's own word for the chapter (downloaded, known, queued...), as the web's table shows it.
    val state: String? = null,
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
            state = it.state,
        )
    }

/**
 * Whether the reader will open [row]: a copy on the device always, the
 * server's file only at home. Anything else the server would have to fetch
 * from its source.
 */
fun readableFrom(row: ChapterRow, home: Boolean): Boolean =
    row.availability == Availability.OnDevice || (home && row.availability == Availability.OnServer)

// Here rather than in the reader so the series screen can say the same thing
// before the reader is ever opened.
const val NOT_ON_DEVICE = "Not on this device. It will be copied the next time you are home."

// Only a chapter the server holds as a file is ever copied, so the promise in
// NOT_ON_DEVICE would be false for one it never downloaded.
const val NOT_DOWNLOADED = "Not downloaded on the server yet."

/** Why the reader would refuse [row] from where the phone is, or null when it would open it. */
fun unreadableReason(row: ChapterRow, home: Boolean): String? = when {
    readableFrom(row, home) -> null
    row.availability == Availability.NotDownloaded -> NOT_DOWNLOADED
    else -> NOT_ON_DEVICE
}
