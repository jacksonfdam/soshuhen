package app.soshuhen.library

import app.soshuhen.api.Series
import kotlin.math.max

// The same arithmetic as frontend/src/features/library/useLibrary.ts, so a
// series shows the same numbers on the phone and on the web.

fun totalChapters(s: Series): Int? = max(s.totalChapters ?: 0, s.known).takeIf { it > 0 }

fun unread(s: Series): Int = totalChapters(s)?.let { max(0, it - s.progress) } ?: 0

val STATUS_ORDER = listOf("reading", "plan_to_read", "completed", "on_hold", "dropped")

val STATUS_LABEL = mapOf(
    "reading" to "Reading",
    "plan_to_read" to "Plan to read",
    "completed" to "Completed",
    "on_hold" to "On hold",
    "dropped" to "Dropped",
)

// A series with reading recorded comes before one without; a series never
// read falls back to its sync time, behind every one that has.
private val byRecentReading = compareByDescending<Series> { it.lastReadAt != null }
    .thenByDescending { it.lastReadAt }
    .thenByDescending { it.updatedAt }

fun continueReading(all: List<Series>): List<Series> = all
    .filter { it.status == "reading" && (it.lastReadAt != null || it.updatedAt != null) }
    .sortedWith(byRecentReading)
    .take(3)

/** Comics only: the app has no reader for prose yet. A null kind is a comic. */
fun comics(all: List<Series>): List<Series> = all.filter { it.kind != "prose" }

fun visible(all: List<Series>, status: String?, query: String): List<Series> {
    val needle = query.trim()
    return comics(all).filter {
        (status == null || it.status == status) &&
            (needle.isEmpty() || it.title.contains(needle, ignoreCase = true))
    }
}
