package app.soshuhen.core

import app.soshuhen.api.Fixtures
import app.soshuhen.db.ImportLogEntity
import app.soshuhen.db.OutboxEntity
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

    @Test fun storageSumsChaptersAndVolumesPerSeries() = runTest {
        val at = Instant.fromEpochMilliseconds(1_000)
        store.indexChapter(DeviceChapter(1, 1, 1.0, "a.cbz", "content://a", null, 100, at))
        store.indexChapter(DeviceChapter(2, 1, 2.0, "b.cbz", "content://b", null, 250, at))
        store.indexVolume(DeviceVolume(9, 2, 1.0, "v.epub", "content://v", null, 4_000, at))
        assertEquals(mapOf(1L to 350L, 2L to 4_000L), store.storageBySeries().first())
        assertEquals(4_350L, store.storageTotal().first())
    }

    @Test fun storageIsZeroWithNothingCopied() = runTest {
        assertEquals(emptyMap(), store.storageBySeries().first())
        assertEquals(0L, store.storageTotal().first())
    }

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

    @Test fun theOutboxKeepsOrderAndDropsByKind() = runTest {
        store.enqueue(OutboxEntity(kind = "position", seriesId = 1, chapterId = 10, page = 3, readAt = "t", body = null))
        store.enqueue(OutboxEntity(kind = "complete", seriesId = 1, chapterId = 10, page = null, readAt = "t", body = null))
        store.enqueue(OutboxEntity(kind = "position", seriesId = 2, chapterId = 20, page = 1, readAt = "t", body = null))
        val queued = store.outbox()
        assertEquals(listOf("position", "complete", "position"), queued.map { it.kind })
        assertTrue(queued.zipWithNext().all { (a, b) -> a.id < b.id })
        store.dropQueued(seriesId = 1, kind = "position")
        assertEquals(listOf("complete", "position"), store.outbox().map { it.kind })
        store.dequeue(store.outbox().first().id)
        assertEquals(listOf(2L), store.outbox().map { it.seriesId })
    }

    @Test fun theImportLogListsNewestFirst() = runTest {
        store.logImport(ImportLogEntity(1, 7, "A", 1.0, importedAt = 100))
        store.logImport(ImportLogEntity(2, 7, "A", 2.0, importedAt = 300))
        store.logImport(ImportLogEntity(3, 8, "B", 1.0, importedAt = 200))
        assertEquals(listOf(2L, 3L, 1L), store.importLog().first().map { it.chapterId })
    }

    @Test fun marksAreKeptApart() = runTest {
        var key = 0L
        store.currentProfile = { key }
        store.mark(5, "frieren")
        key = 7
        assertEquals(emptySet(), store.markedIds().first())
        assertTrue(store.markedByOthers(5))
        assertFalse(store.isMarked(5).first())
        key = 0
        assertEquals(setOf(5L), store.markedIds().first())
        assertFalse(store.markedByOthers(5))
    }

    @Test fun snapshotsAreKeptApart() = runTest {
        var key = 7L
        store.currentProfile = { key }
        store.saveSeries(Fixtures.SERIES)
        key = 0
        assertNull(store.seriesSnapshot())
        store.saveSeries("[]")
        key = 7
        assertEquals(2, store.seriesSnapshot()!!.size)
    }

    @Test fun theManagerKeepsUnprefixedSnapshots() = runTest {
        // What an install wrote before profiles is under the plain key.
        store.putValue("series", Fixtures.SERIES)
        store.currentProfile = { 0L }
        assertEquals(2, store.seriesSnapshot()!!.size)
    }

    @Test fun theProfileListIsTheServers() = runTest {
        store.currentProfile = { 7L }
        store.putProfiles("""[{"id":1,"name":"Me","avatar":"avatar-01","has_pin":false,"is_manager":true,"position":0}]""")
        store.currentProfile = { 0L }
        assertEquals(listOf("Me"), store.profilesSnapshot()!!.map { it.name })
    }
}
