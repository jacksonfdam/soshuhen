package app.soshuhen.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class StorageTest {
    @Test fun thePhonesOwnStorageIsEmulatedZero() {
        assertEquals(
            "/storage/emulated/0",
            storageRoot("content://com.android.externalstorage.documents/tree/primary%3AManga"),
        )
    }

    @Test fun aCardIsMountedByItsId() {
        assertEquals(
            "/storage/1A2B-3C4D",
            storageRoot("content://com.android.externalstorage.documents/tree/1A2B-3C4D%3ASoshuhen"),
        )
    }

    @Test fun anUnknownUriHasNoRoot() {
        assertNull(storageRoot("content://tree/Manga"))
        assertNull(storageRoot("content://x/tree/..%2Fetc%3Ay"))
    }
}
