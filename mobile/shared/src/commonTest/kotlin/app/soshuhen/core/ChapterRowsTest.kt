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
}
