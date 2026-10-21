package app.soshuhen.detail

import app.soshuhen.api.Resume
import app.soshuhen.api.Series
import app.soshuhen.api.SeriesChapter
import app.soshuhen.api.SeriesDetail
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val CBZ = "/manga/s/c.cbz"

fun detail(progress: Int, chapters: List<SeriesChapter> = defaultChapters()) =
    SeriesDetail(Series(id = 1, title = "S", slug = "s", progress = progress), chapters)

fun defaultChapters() = listOf(
    SeriesChapter(10, 1.0, state = "downloaded", filePath = CBZ),
    SeriesChapter(20, 2.0, state = "known"),
    SeriesChapter(25, 2.5, state = "downloaded", filePath = CBZ),
    SeriesChapter(30, 3.0, state = "downloaded", filePath = CBZ),
)

class DetailRulesTest {
    @Test fun rowsAreNewestFirst() {
        assertEquals(listOf(3.0, 2.5, 2.0, 1.0), chapterRows(detail(progress = 0)).map { it.number })
    }

    @Test fun readIsByWholeChapter() {
        val rows = chapterRows(detail(progress = 2))
        assertTrue(rows.single { it.number == 2.5 }.read)
        assertFalse(rows.single { it.number == 3.0 }.read)
    }

    @Test fun downloadedWithAFileIsOnServer() {
        val rows = chapterRows(
            detail(
                0,
                listOf(
                    SeriesChapter(1, 1.0, state = "downloaded", filePath = CBZ),
                    SeriesChapter(2, 2.0, state = "downloaded", filePath = null),
                    SeriesChapter(3, 3.0, state = "known"),
                ),
            ),
        ).associate { it.id to it.availability }
        assertEquals(mapOf(1L to Availability.OnServer, 2L to Availability.NotDownloaded, 3L to Availability.NotDownloaded), rows)
    }

    @Test fun continueUsesTheServersResume() {
        assertEquals(20L, continueChapter(detail(progress = 3), Resume(20, 4))?.id)
    }

    @Test fun continueFallsBackToFirstUnreadOnServer() {
        assertEquals(25L, continueChapter(detail(progress = 1), null)?.id)
    }

    @Test fun resumePointingAtAChapterNotListedFallsBack() {
        assertEquals(25L, continueChapter(detail(progress = 1), Resume(999, 0))?.id)
    }

    @Test fun nothingToContinueIsNull() {
        assertNull(continueChapter(detail(progress = 3), null))
    }
}
