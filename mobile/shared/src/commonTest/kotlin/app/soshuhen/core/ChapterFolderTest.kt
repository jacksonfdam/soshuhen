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

    @Test fun aRefusedCreateInAFolderStillThereIsAFullDevice() {
        assertIs<DeviceFull>(refusedToCreate(folderAvailable = true, "Ch 1.cbz"))
        assertIs<FolderUnavailable>(refusedToCreate(folderAvailable = false, "Ch 1.cbz"))
    }
}
