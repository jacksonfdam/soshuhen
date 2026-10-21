package app.soshuhen.core

import app.soshuhen.api.Fixtures
import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class LocalStoreTest {
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore

    @BeforeTest fun setUp() {
        db = testDatabase()
        store = LocalStore(db) { Instant.fromEpochMilliseconds(1_000) }
    }

    @AfterTest fun tearDown() = db.close()

    private fun chapter(id: Long, series: Long) =
        DeviceChapter(id, series, 1.0, "c.cbz", "content://c", null, 10, Instant.fromEpochMilliseconds(1_000))

    @Test fun aSavedLibraryReadsBack() = runTest {
        store.saveSeries(Fixtures.SERIES)
        assertEquals(2, store.seriesSnapshot()!!.size)
    }

    @Test fun noSnapshotIsNull() = runTest { assertNull(store.seriesSnapshot()) }

    @Test fun aSavedDetailReadsBack() = runTest {
        store.saveDetail(1, Fixtures.DETAIL)
        assertEquals(3, store.detailSnapshot(1)!!.chapters.size)
        assertNull(store.detailSnapshot(2))
    }

    @Test fun markingIsRemembered() = runTest {
        store.mark(7, "s")
        assertTrue(store.isMarked(7).first())
        assertEquals(setOf(7L), store.markedIds().first())
        store.unmark(7)
        assertFalse(store.isMarked(7).first())
    }

    @Test fun unmarkingKeepsTheIndexedChapters() = runTest {
        store.mark(7, "s")
        store.indexChapter(chapter(70, series = 7))
        store.unmark(7)
        assertEquals(1, store.deviceChapters(7).first().size)
        assertEquals(setOf(70L), store.allDeviceChapterIds().first())
        store.forgetChapter(70)
        assertTrue(store.deviceChapters(7).first().isEmpty())
    }

    @Test fun theProblemIsOneRow() = runTest {
        store.setProblem("a")
        store.setProblem("b")
        assertEquals("b", store.problem().first())
        store.setProblem(null)
        assertNull(store.problem().first())
    }
}
