package app.soshuhen.core

import app.soshuhen.db.ImportLogEntity
import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class VolumeStoreTest {
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore

    @BeforeTest fun setUp() {
        db = testDatabase()
        store = LocalStore(db)
    }

    @AfterTest fun tearDown() = db.close()

    private fun volume(id: Long, series: Long = 308, number: Double = 1.0) =
        DeviceVolume(id, series, number, "v$id.epub", "content://v$id", "\"e$id\"", 10, Instant.fromEpochMilliseconds(5))

    @Test fun partEtagsOfAChapterAndAVolumeWithTheSameIdAreApart() = runTest {
        store.savePartEtag(BookRef(BookKind.Chapter, 7), "\"a\"")
        store.savePartEtag(BookRef(BookKind.Volume, 7), "\"b\"")
        assertEquals("\"a\"", store.partEtag(BookRef(BookKind.Chapter, 7)))
        assertEquals("\"b\"", store.partEtag(BookRef(BookKind.Volume, 7)))
        store.forgetPart(BookRef(BookKind.Chapter, 7))
        assertNull(store.partEtag(BookRef(BookKind.Chapter, 7)))
        assertEquals("\"b\"", store.partEtag(BookRef(BookKind.Volume, 7)))
    }

    @Test fun aVolumeIndexReadsBack() = runTest {
        store.indexVolume(volume(41))
        assertEquals(volume(41), store.deviceVolume(41))
        assertEquals(listOf(volume(41)), store.deviceVolumes(308).first())
        assertEquals(setOf(308L), store.seriesWithChapters().first())
        store.forgetVolume(41)
        assertNull(store.deviceVolume(41))
    }

    @Test fun anUnreadableVolumeMatchesNoServerEtag() = runTest {
        store.indexVolume(volume(41))
        store.markVolumeUnreadable(41)
        assertEquals("unreadable", store.deviceVolume(41)?.etag)
    }

    // A finished volume shows as read only while the server has not heard of
    // it; once sent, the lists' count decides, as it does on the web.
    @Test fun volumeProgressIsTheCompletionsStillQueued() = runTest {
        val outbox = Outbox(store) { Instant.fromEpochMilliseconds(0) }
        assertNull(store.volumeProgress(308))
        store.indexVolume(volume(41, number = 3.0))
        store.indexVolume(volume(42, number = 2.0))
        outbox.completeVolume(308, 41)
        outbox.completeVolume(308, 42)
        assertEquals(3, store.volumeProgress(308))
        assertNull(store.volumeProgress(309))
        store.outbox().forEach { store.dequeue(it.id) }
        assertNull(store.volumeProgress(308))
    }

    // A volume finished from the server's copy at home, then queued while away.
    @Test fun aQueuedVolumeNotOnTheDeviceIsNumberedFromTheDetail() = runTest {
        store.saveDetail(308, app.soshuhen.api.Fixtures.PROSE_DETAIL)
        Outbox(store) { Instant.fromEpochMilliseconds(0) }.completeVolume(308, 41)
        assertEquals(1, store.volumeProgress(308))
    }

    @Test fun switchingServerForgetsVolumes() = runTest {
        store.belongTo("first")
        store.indexVolume(volume(41))
        store.belongTo("second")
        assertTrue(store.deviceVolumes(308).first().isEmpty())
    }

    @Test fun theLogKeepsAChapterAndAVolumeWithTheSameId() = runTest {
        store.logImport(ImportLogEntity(7, 308, "T", 1.0, importedAt = 100))
        store.logImport(ImportLogEntity(7, 308, "T", 1.0, importedAt = 200, kind = BookKind.Volume.key))
        assertEquals(listOf("volume", "chapter"), store.importLog().first().map { it.kind })
    }
}
