package app.soshuhen.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class ChapterFolderTest {
    @Test fun aFreshCopyTruncatesWhatWasThere() {
        // A restarted copy over a longer .part would otherwise keep its old tail.
        assertEquals("wt", writeMode(append = false))
        assertEquals("wa", writeMode(append = true))
    }

    @Test fun aRefusedCreateIsAFullDeviceOnlyWhenSpaceIsActuallyLow() {
        assertIs<DeviceFull>(refusedToCreate(folderAvailable = true, freeBytes = 1_000_000, "Ch 1.cbz"))
        assertIs<DeviceFull>(refusedToCreate(folderAvailable = true, freeBytes = 0, "Ch 1.cbz"))
    }

    @Test fun aRefusedCreateWithRoomToSpareIsNotAFullDevice() {
        // A Galaxy Tab reported a full device with 109 GB free on the card.
        val e = refusedToCreate(folderAvailable = true, freeBytes = 109_000_000_000, "Ch 1.cbz")
        assertIs<CannotCreate>(e)
        assertEquals("Ch 1.cbz", e.name)
    }

    @Test fun aRefusedCreateWithUnknownSpaceIsNotAFullDevice() {
        assertIs<CannotCreate>(refusedToCreate(folderAvailable = true, freeBytes = null, "Ch 1.cbz"))
    }

    @Test fun aRefusedCreateInAFolderThatWentAwayIsTheFolder() {
        assertIs<FolderUnavailable>(refusedToCreate(folderAvailable = false, freeBytes = 0, "Ch 1.cbz"))
    }
}
