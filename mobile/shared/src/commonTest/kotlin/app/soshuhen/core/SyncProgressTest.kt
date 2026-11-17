package app.soshuhen.core

import kotlin.test.Test
import kotlin.test.assertEquals

class SyncProgressTest {
    @Test fun before_anything_is_known() {
        assertEquals("Checking what the server holds…", progressText(SyncProgress.Starting))
    }

    @Test fun reading_series_counts_from_one() {
        assertEquals("Reading series 3 of 40 from the server…", progressText(SyncProgress.Reading(2, 40)))
    }

    @Test fun a_chapter_being_copied_is_named() {
        val p = SyncProgress.Item(104, 385, copied = 12, title = "Gin Tama", kind = BookKind.Chapter, number = 301.0, copying = true)
        assertEquals("105 of 385 · 12 copied\nCopying Gin Tama · Ch. 301", progressText(p))
    }

    @Test fun a_chapter_being_checked_says_so() {
        val p = SyncProgress.Item(0, 385, copied = 0, title = "Gin Tama", kind = BookKind.Chapter, number = 12.5, copying = false)
        assertEquals("1 of 385 · 0 copied\nChecking Gin Tama · Ch. 12.5", progressText(p))
    }

    @Test fun a_volume_is_named_as_one() {
        val p = SyncProgress.Item(0, 2, copied = 0, title = "Ascendance", kind = BookKind.Volume, number = 3.0, copying = true)
        assertEquals("1 of 2 · 0 copied\nCopying Ascendance · Vol. 3", progressText(p))
    }

    @Test fun verifying_the_device_counts_from_one() {
        assertEquals("Checking files on this device: 120 of 385…", progressText(SyncProgress.Verifying(119, 385)))
    }

    @Test fun waiting_for_a_running_copy_shows_that_copy() {
        val inner = SyncProgress.Item(4, 20, copied = 3, title = "Gin Tama", kind = BookKind.Chapter, number = 7.0, copying = true)
        assertEquals(
            "Waiting for the copy already running\n5 of 20 · 3 copied\nCopying Gin Tama · Ch. 7",
            progressText(SyncProgress.Waiting(inner)),
        )
    }
}
