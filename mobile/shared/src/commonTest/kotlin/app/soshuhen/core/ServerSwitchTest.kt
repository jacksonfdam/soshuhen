package app.soshuhen.core

import app.soshuhen.api.Fixtures
import app.soshuhen.api.Resume
import app.soshuhen.db.ImportLogEntity
import app.soshuhen.db.SoshuhenDatabase
import app.soshuhen.server.SavedServer
import app.soshuhen.server.ServerAddress
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class ServerSwitchTest {
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private val folder = FakeChapterFolder()

    @BeforeTest fun setUp() {
        db = testDatabase()
        store = LocalStore(db) { Instant.fromEpochMilliseconds(1_000) }
    }

    @AfterTest fun tearDown() = db.close()

    private fun server(instance: String, host: String = "10.0.0.5") = SavedServer(ServerAddress("http", host, 8080), instance)

    private suspend fun fillForTheFirstServer() {
        store.saveSeries(Fixtures.SERIES)
        store.saveDetail(1, Fixtures.DETAIL)
        store.saveResume(1, Resume(11, 3))
        store.mark(1, "frieren")
        val uri = folder.put("frieren", "c.cbz")
        store.indexChapter(DeviceChapter(11, 1, 1.0, "c.cbz", uri, "\"e\"", 3, Instant.fromEpochMilliseconds(1_000)))
        Outbox(store) { Instant.fromEpochMilliseconds(2_000) }.complete(1, 11)
        store.savePartEtag(13, "\"p\"")
        store.setProblem("Device full: free some space or delete read chapters")
        store.logImport(ImportLogEntity(11, 1, "Frieren", 1.0, 1_000))
    }

    @Test fun anotherInstallationStartsFromNothingButTheFiles() = runTest {
        val servers = InstanceGuard(FakeServerStore(), store)
        servers.save(server("first"))
        fillForTheFirstServer()
        servers.clear()
        servers.save(server("second", host = "10.0.0.6"))

        assertNull(store.seriesSnapshot())
        assertNull(store.detailSnapshot(1))
        assertNull(store.resume(1))
        assertFalse(store.isMarked(1).first())
        assertNull(store.deviceChapter(11))
        assertTrue(store.outbox().isEmpty())
        assertNull(store.partEtag(13))
        assertNull(store.problem().first())
        // Its series ids are the old server's: sending them to this one would
        // move unrelated list progress. The files themselves are the user's.
        assertEquals(setOf(folder.uri("frieren", "c.cbz")), folder.files.keys)
        assertEquals("second", servers.saved.first()?.instanceId)
    }

    @Test fun theSameInstallationAtANewAddressKeepsEverything() = runTest {
        val servers = InstanceGuard(FakeServerStore(), store)
        servers.save(server("first"))
        fillForTheFirstServer()
        servers.clear()
        servers.save(server("first", host = "10.0.0.7"))

        assertTrue(store.isMarked(1).first())
        assertNotNull(store.deviceChapter(11))
        assertEquals(1, store.outbox().size)
        assertNotNull(store.detailSnapshot(1))
    }

    @Test fun anInstallFromBeforeTheGuardIsAdoptedNotCleared() = runTest {
        // Data written by a version that never recorded whose it was.
        fillForTheFirstServer()
        InstanceGuard(FakeServerStore(), store).save(server("first"))
        assertTrue(store.isMarked(1).first())
        assertNotNull(store.deviceChapter(11))
    }

    @Test fun aSwitchKilledHalfWayKeepsTheOldInstallationWhole() = runTest {
        val servers = InstanceGuard(FakeServerStore(), store)
        servers.save(server("first"))
        fillForTheFirstServer()
        store.beforeRecordingInstance = { error("process killed") }
        runCatching { store.belongTo("second") }
        store.beforeRecordingInstance = {}

        // Rolled back: the next save still sees "first" and clears properly,
        // instead of finding no key and adopting the old marks as the new server's.
        assertTrue(store.isMarked(1).first())
        assertNotNull(store.deviceChapter(11))
        store.belongTo("second")
        assertFalse(store.isMarked(1).first())
        assertNull(store.deviceChapter(11))
    }
}
