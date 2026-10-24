package app.soshuhen.library

import app.soshuhen.api.Series
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

fun series(
    id: Long = 1,
    title: String = "S",
    total: Int? = null,
    known: Int = 0,
    progress: Int = 0,
    kind: String? = "comic",
    status: String? = "reading",
    lastReadAt: String? = null,
    updatedAt: String? = null,
) = Series(
    id = id, title = title, slug = "s$id", totalChapters = total, known = known, progress = progress,
    kind = kind, status = status, lastReadAt = lastReadAt?.let(Instant::parse), updatedAt = updatedAt?.let(Instant::parse),
)

class LibraryRulesTest {
    @Test fun totalUsesTheHigherOfTotalAndKnown() {
        assertEquals(141, totalChapters(series(total = 120, known = 141)))
    }

    @Test fun noTotalAndNoneKnownIsNull() {
        assertNull(totalChapters(series(total = null, known = 0)))
    }

    @Test fun unreadIsTotalMinusProgress() {
        assertEquals(3, unread(series(total = 141, progress = 138)))
    }

    @Test fun unreadNeverNegative() {
        assertEquals(0, unread(series(total = 10, progress = 12)))
    }

    @Test fun continueReadingTakesThreeReadingSeriesMostRecentFirst() {
        val all = listOf(
            series(1, lastReadAt = "2026-10-01T00:00:00Z"),
            series(2, lastReadAt = "2026-10-05T00:00:00Z"),
            series(3, status = "completed", lastReadAt = "2026-10-09T00:00:00Z"),
            series(4, lastReadAt = "2026-10-03T00:00:00Z"),
            series(5, updatedAt = "2026-10-08T00:00:00Z"),
            series(6),
        )
        assertEquals(listOf(2L, 4L, 1L), continueReading(all).map { it.id })
    }

    @Test fun aSeriesNeverReadFallsBehindOnesThatWere() {
        val all = listOf(series(1, updatedAt = "2026-10-09T00:00:00Z"), series(2, lastReadAt = "2026-01-01T00:00:00Z"))
        assertEquals(listOf(2L, 1L), continueReading(all).map { it.id })
    }

    @Test fun novelsAreVisible() {
        assertEquals(1, visible(listOf(series(kind = "prose")), null, "").size)
    }

    // The provider's own format names a novel best; a novel without one still says what it is.
    @Test fun aNovelWithoutAFormatIsLabelledNovel() {
        assertEquals("Novel", coverFormat(series(kind = "prose")))
        assertEquals("Light Novel", coverFormat(series(kind = "prose").copy(format = "light_novel")))
        assertEquals(null, coverFormat(series(kind = "comic")))
    }

    @Test fun nullKindIsAComic() {
        assertEquals(1, visible(listOf(series(kind = null)), null, "").size)
    }

    @Test fun statusFilters() {
        val all = listOf(series(1, status = "reading"), series(2, status = "completed"))
        assertEquals(listOf(2L), visible(all, "completed", "").map { it.id })
        assertEquals(2, visible(all, null, "").size)
    }

    @Test fun searchIgnoresCase() {
        assertEquals(1, visible(listOf(series(title = "Frieren")), null, "frie").size)
    }

    @Test fun onDeviceTabShowsOnlyMarked() {
        assertEquals(listOf(2L), visible(listOf(series(1), series(2)), ON_DEVICE, "", marked = setOf(2)).map { it.id })
    }

    @Test fun onDeviceIgnoresReadingStatus() {
        val all = listOf(series(1, status = "completed"), series(2, status = null))
        assertEquals(listOf(1L, 2L), visible(all, ON_DEVICE, "", marked = setOf(1, 2)).map { it.id })
    }

    @Test fun atHomeEverySeriesIsReachable() {
        assertTrue(reachable(series(1), atHome = true, marked = emptySet()))
    }

    @Test fun awayOnlyAMarkedSeriesIsReachable() {
        assertTrue(reachable(series(1), atHome = false, marked = setOf(1)))
        assertFalse(reachable(series(2), atHome = false, marked = setOf(1)))
    }
}
