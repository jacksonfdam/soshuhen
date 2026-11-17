package app.soshuhen.core

import app.soshuhen.api.OffloadRequest
import app.soshuhen.api.OffloadResult
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class SyncTest {
    private lateinit var db: app.soshuhen.db.SoshuhenDatabase
    private lateinit var store: LocalStore
    private val folder = FakeChapterFolder()
    private val sent = mutableListOf<OffloadRequest>()
    private var home = true
    private var imports = 0
    private val scopes = mutableListOf<Set<Long>?>()

    private val detailJson = """{"series": {"id": 1, "title": "Frieren", "slug": "frieren"},
        "chapters": [{"id": 1, "number": 1, "state": "downloaded", "file_path": "/manga/frieren/c1.cbz"}]}"""

    private fun sync() = Sync(
        importRun = { scope, _ -> imports++; scopes += scope; ImportReport(emptyMap(), emptyMap(), 0, null) },
        store = store,
        folder = folder,
        atHome = { home },
        offload = { request -> sent += request; OffloadResult(queued = request.chapters.size + request.volumes.size) },
    )

    @BeforeTest fun setUp() {
        db = testDatabase()
        store = LocalStore(db) { Instant.fromEpochMilliseconds(1_000) }
    }

    @AfterTest fun tearDown() = db.close()

    private suspend fun holdChapterOne() {
        store.mark(1, "frieren")
        store.saveDetail(1, detailJson)
        folder.files[folder.uri("frieren", "c1.cbz")] = ByteArray(100)
        store.indexChapter(DeviceChapter(1, 1, 1.0, "c1.cbz", folder.uri("frieren", "c1.cbz"), "\"e\"", 100, Instant.fromEpochMilliseconds(1)))
    }

    @Test fun sync_imports_then_reports_verified() = runTest {
        holdChapterOne()
        val report = sync().run(scope = null)
        assertEquals(1, imports)
        assertTrue(report.allVerified)
    }

    @Test fun sync_reports_checking_each_held_file() = runTest {
        holdChapterOne()
        val steps = mutableListOf<SyncProgress>()
        sync().run(scope = null) { steps += it }
        assertEquals(listOf(SyncProgress.Verifying(0, 1), SyncProgress.Verifying(1, 1)), steps.filterIsInstance<SyncProgress.Verifying>())
    }

    @Test fun sync_of_one_series_copies_only_that_series() = runTest {
        holdChapterOne()
        sync().run(scope = setOf(1L))
        sync().run(scope = null)
        assertEquals(listOf(setOf(1L), null), scopes)
    }

    @Test fun sync_away_from_home_does_nothing() = runTest {
        holdChapterOne()
        home = false
        val report = sync().run(scope = null)
        assertEquals(0, imports)
        assertNotNull(report.problem)
    }

    @Test fun sync_scope_limits_to_one_series() = runTest {
        holdChapterOne()
        store.mark(2, "other")
        store.saveDetail(2, detailJson.replace("\"id\": 1, \"title\"", "\"id\": 2, \"title\"").replace("\"id\": 1, \"number\"", "\"id\": 5, \"number\""))
        val report = sync().run(scope = setOf(1L))
        assertEquals(1, report.seriesCount)
        assertTrue(report.allVerified)
    }

    @Test fun sync_offload_refuses_unverified_report() = runTest {
        val report = SyncReport(1, emptyList(), listOf(Missing(BookRef(BookKind.Chapter, 1), MissingReason.NotCopied)), emptyList())
        assertFailsWith<IllegalStateException> { sync().offload(report) }
        assertTrue(sent.isEmpty())
    }

    @Test fun sync_offload_posts_held_items() = runTest {
        holdChapterOne()
        val s = sync()
        val result = s.offload(s.run(scope = null))
        assertEquals(1, result.queued)
        assertEquals("\"e\"", sent.single().chapters.single().etag)
        assertEquals(100L, sent.single().chapters.single().size)
    }
}
