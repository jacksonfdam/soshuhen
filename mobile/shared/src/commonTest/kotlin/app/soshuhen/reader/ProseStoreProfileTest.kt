package app.soshuhen.reader

import app.soshuhen.core.BookKind
import app.soshuhen.core.BookRef
import app.soshuhen.core.LocalStore
import app.soshuhen.core.testDatabase
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ProseStoreProfileTest {
    @Test fun aPlaceInABookIsEachProfilesOwn() = runTest {
        val db = testDatabase()
        try {
            val local = LocalStore(db)
            val prose = ProseStore(local)
            val book = BookRef(BookKind.Volume, 3)
            var key = 7L
            local.currentProfile = { key }
            prose.saveMode(1, "long_strip")
            prose.savePosition(book, ProsePosition(4, 0, 10))
            key = 0
            assertNull(prose.position(book))
            assertNull(prose.mode(1))
            key = 7
            assertEquals("long_strip", prose.mode(1))
        } finally {
            db.close()
        }
    }
}
