package app.soshuhen.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ChapterRowsTest {
    private fun row(availability: Availability) = ChapterRow(1, 1.0, null, read = false, availability = availability)

    @Test fun onDeviceReadsAnywhere() {
        assertNull(unreadableReason(row(Availability.OnDevice), home = false))
        assertNull(unreadableReason(row(Availability.OnDevice), home = true))
    }

    @Test fun onServerReadsAtHome() = assertNull(unreadableReason(row(Availability.OnServer), home = true))

    @Test fun onServerAwaySaysItWillBeCopied() =
        assertEquals(NOT_ON_DEVICE, unreadableReason(row(Availability.OnServer), home = false))

    @Test fun notDownloadedSaysSoEverywhere() {
        assertEquals(NOT_DOWNLOADED, unreadableReason(row(Availability.NotDownloaded), home = true))
        assertEquals(NOT_DOWNLOADED, unreadableReason(row(Availability.NotDownloaded), home = false))
    }

    @Test fun offloaded_on_device_row_label() {
        val detail = app.soshuhen.api.SeriesDetail(
            app.soshuhen.api.Series(id = 1, title = "S", slug = "s"),
            listOf(app.soshuhen.api.SeriesChapter(4, 4.0, state = "offloaded"), app.soshuhen.api.SeriesChapter(5, 5.0, state = "downloaded", filePath = "/x")),
        )
        val rows = chapterRows(detail, onDevice = setOf(4L, 5L)).associateBy { it.id }
        kotlin.test.assertEquals("On device only", deviceLabel(rows.getValue(4)))
        kotlin.test.assertEquals("On device", deviceLabel(rows.getValue(5)))
        kotlin.test.assertTrue(rows.getValue(4).onlyCopy)
    }

    @Test fun offloaded_not_on_device_says_how_to_get_it_back() {
        val detail = app.soshuhen.api.SeriesDetail(
            app.soshuhen.api.Series(id = 1, title = "S", slug = "s"),
            listOf(app.soshuhen.api.SeriesChapter(4, 4.0, state = "offloaded")),
        )
        val row = chapterRows(detail).single()
        kotlin.test.assertEquals(Availability.NotDownloaded, row.availability)
        kotlin.test.assertEquals(REMOVED_FROM_SERVER, unreadableReason(row, home = true))
        kotlin.test.assertEquals("Removed from server — download again from the web", REMOVED_FROM_SERVER)
    }

    @Test fun a_device_copy_the_server_no_longer_holds_is_the_only_copy() {
        // A failed or cancelled download again leaves the row known or failed,
        // and the device copy is still the only one.
        for (state in listOf("queued", "downloading", "failed", "known")) {
            val detail = app.soshuhen.api.SeriesDetail(
                app.soshuhen.api.Series(id = 1, title = "S", slug = "s"),
                listOf(app.soshuhen.api.SeriesChapter(4, 4.0, state = state)),
            )
            val row = chapterRows(detail, onDevice = setOf(4L)).single()
            kotlin.test.assertTrue(row.onlyCopy, state)
            kotlin.test.assertEquals("On device only", deviceLabel(row), state)
        }
    }
}
