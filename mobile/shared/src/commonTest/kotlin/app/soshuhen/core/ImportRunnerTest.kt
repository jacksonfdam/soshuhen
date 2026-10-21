package app.soshuhen.core

import app.soshuhen.api.Identity
import app.soshuhen.api.Series
import app.soshuhen.api.SeriesChapter
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.db.SoshuhenDatabase
import app.soshuhen.server.SavedServer
import app.soshuhen.server.ServerAddress
import app.soshuhen.server.ServerLocator
import app.soshuhen.server.ServerScanner
import app.soshuhen.server.identity
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Duration
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Instant

private object QuietNetwork : NetworkInfo {
    override fun wifiAddress(): Pair<String, Int>? = null

    // The runner asks for the location itself; a check started by the session
    // would add a second identity probe to the request log.
    override val changes: Flow<Unit> = emptyFlow()
}

@OptIn(ExperimentalCoroutinesApi::class)
class ImportRunnerTest {
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private lateinit var folder: FakeChapterFolder
    private var now = Instant.parse("2026-10-21T08:00:00Z")
    private val clock = { now }

    private val log = mutableListOf<String>()
    private val series = mutableListOf<Series>()
    private val chapters = mutableMapOf<Long, List<SeriesChapter>>()
    private val archives = mutableMapOf<Long, Pair<ByteArray, String>>()
    private var copyTime: Duration = Duration.ZERO
    private var archiveStatus: HttpStatusCode? = null
    private var declaredLength: Long? = null
    private var onArchive: (Long) -> Unit = {}
    private var home = true

    // Bytes whose text starts with BAD are what a truncated archive looks like to the check.
    private val check = ArchiveCheck { source ->
        val text = source.use { okio.Buffer().apply { writeAll(it) }.readUtf8() }
        if (text.startsWith("BAD")) 0 else 1
    }

    @BeforeTest fun setUp() {
        db = testDatabase()
        store = LocalStore(db) { now }
        folder = FakeChapterFolder()
    }

    @AfterTest fun tearDown() = db.close()

    private fun addSeries(id: Long, slug: String, vararg list: SeriesChapter) {
        series += Series(id = id, title = "Title $id", slug = slug)
        chapters[id] = list.toList()
    }

    private fun downloaded(id: Long, number: Double) =
        SeriesChapter(id, number, state = "downloaded", filePath = "/manga/s/Ch $number.cbz")

    private fun serve(id: Long, text: String = "PK chapter $id ".repeat(20), etag: String = "\"e$id\"") {
        archives[id] = text.encodeToByteArray() to etag
    }

    private fun file(slug: String, number: Double) = folder.uri(slug, "Ch $number.cbz")

    private fun TestScope.runner(): ImportRunner {
        val engine = MockEngine(
            MockEngineConfig().apply {
                dispatcher = StandardTestDispatcher(testScheduler)
                addHandler { request ->
                    val path = request.url.encodedPath
                    val range = request.headers[HttpHeaders.Range]
                    val ifRange = request.headers[HttpHeaders.IfRange]
                    log += "${request.method.value} $path" + (range?.let { " $it" } ?: "") + (ifRange?.let { " if-range $it" } ?: "")
                    val json = headersOf(HttpHeaders.ContentType, "application/json")
                    when {
                        request.method == HttpMethod.Put -> respond("{}", HttpStatusCode.OK, json)
                        path == "/api/series" -> respond(SoshuhenJson.encodeToString(series.toList()), HttpStatusCode.OK, json)
                        path.startsWith("/api/series/") -> {
                            val id = path.removePrefix("/api/series/").toLong()
                            val s = series.first { it.id == id }
                            respond(SoshuhenJson.encodeToString(SeriesDetail(s, chapters.getValue(id))), HttpStatusCode.OK, json)
                        }
                        path.startsWith("/api/chapters/") -> {
                            archiveStatus?.let { return@addHandler respond("", it) }
                            val id = path.removePrefix("/api/chapters/").removeSuffix("/archive").toLong()
                            onArchive(id)
                            val (bytes, etag) = archives[id] ?: return@addHandler respond("", HttpStatusCode.NotFound)
                            // As Starlette: an If-Range that no longer matches gets the whole file.
                            val start = range?.removePrefix("bytes=")?.removeSuffix("-")?.toLong()
                                ?.takeIf { ifRange == null || ifRange == etag }
                            when {
                                start == null -> {
                                    now += copyTime
                                    respond(
                                        bytes, HttpStatusCode.OK,
                                        headersOf(
                                            HttpHeaders.ETag to listOf(etag),
                                            HttpHeaders.ContentLength to listOf("${declaredLength ?: bytes.size}"),
                                        ),
                                    )
                                }
                                start >= bytes.size -> respond(
                                    "", HttpStatusCode.RequestedRangeNotSatisfiable,
                                    headersOf(HttpHeaders.ContentRange, "bytes */${bytes.size}"),
                                )
                                else -> {
                                    now += copyTime
                                    respond(
                                        bytes.copyOfRange(start.toInt(), bytes.size), HttpStatusCode.PartialContent,
                                        headersOf(
                                            HttpHeaders.ETag to listOf(etag),
                                            HttpHeaders.ContentRange to listOf("bytes $start-${bytes.size - 1}/${bytes.size}"),
                                            HttpHeaders.ContentLength to listOf("${bytes.size - start}"),
                                        ),
                                    )
                                }
                            }
                        }
                        else -> respond("", HttpStatusCode.NotFound)
                    }
                }
            },
        )
        val probe: suspend (ServerAddress) -> Identity? = { log += "identity"; if (home) identity(id = "id-1") else null }
        val saved = SavedServer(ServerAddress("http", "10.0.0.5", 8080), "id-1")
        val session = Session(
            FakeServerStore(saved), ServerLocator(probe, ServerScanner(probe)), QuietNetwork,
            soshuhenHttpClient(engine), backgroundScope,
        )
        runCurrent()
        return ImportRunner(session, store, folder, Outbox(store, clock), check, clock)
    }

    private suspend fun indexed(chapterId: Long) = store.deviceChapter(chapterId)

    private fun archiveRequests() = log.filter { it.startsWith("GET /api/chapters/") }

    @Test fun awayFromHomeDoesNothing() = runTest {
        home = false
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        Outbox(store, clock).complete(1, 10)
        val report = runner().run()
        assertEquals(ImportReport(emptyMap(), emptyMap(), pending = 0, problem = null), report)
        assertEquals(listOf("identity"), log)
        assertEquals(1, store.outbox().size)
        assertTrue(folder.files.isEmpty())
    }

    @Test fun copiesOnlyMarkedDownloadedChapters() = runTest {
        addSeries(
            1, "one", downloaded(10, 1.0),
            SeriesChapter(11, 2.0, state = "known"),
            SeriesChapter(12, 3.0, state = "downloaded", filePath = null),
        )
        addSeries(2, "two", downloaded(20, 1.0))
        serve(10); serve(20)
        store.mark(1, "one")
        val report = runner().run()
        assertEquals(listOf("GET /api/chapters/10/archive"), archiveRequests())
        assertEquals(mapOf(1L to listOf(1.0)), report.imported)
        assertEquals(mapOf(1L to "Title 1"), report.seriesTitles)
        assertEquals(0, report.pending)
        assertNull(report.problem)
        assertContentEquals(archives.getValue(10).first, folder.files[file("one", 1.0)])
        val row = indexed(10)!!
        assertEquals(file("one", 1.0), row.uri)
        assertEquals("\"e10\"", row.etag)
        assertEquals("Ch 1.0.cbz", row.fileName)
        assertEquals(1, store.importLog().first().size)
        assertTrue(store.seriesSnapshot()!!.size == 2)
        assertTrue(store.detailSnapshot(1) != null)
        assertNull(store.detailSnapshot(2))
    }

    @Test fun anIndexedChapterWithTheSameEtagIsSkipped() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        runner().run()
        log.clear()
        val before = indexed(10)
        now += 60.minutes
        val report = runner().run()
        assertTrue(report.imported.isEmpty())
        assertEquals(0, report.pending)
        assertEquals(before, indexed(10))
        // Asked for the last byte only: enough to read the ETag without the archive.
        val size = archives.getValue(10).first.size
        assertEquals(listOf("GET /api/chapters/10/archive bytes=${size - 1}-"), archiveRequests())
    }

    @Test fun aChangedEtagIsCopiedAgain() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        runner().run()
        serve(10, text = "PK rebuilt ".repeat(30), etag = "\"e10-new\"")
        val report = runner().run()
        assertEquals(mapOf(1L to listOf(1.0)), report.imported)
        assertEquals("\"e10-new\"", indexed(10)!!.etag)
        assertContentEquals(archives.getValue(10).first, folder.files[file("one", 1.0)])
        assertFalse(folder.files.keys.any { it.endsWith(".part") })
    }

    @Test fun anInterruptedCopyResumesWithRange() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        val original = archives.getValue(10).first
        folder.files[file("one", 1.0) + ".part"] = original.copyOfRange(0, 100)
        store.savePartEtag(10, "\"e10\"")
        runner().run()
        assertEquals(listOf("GET /api/chapters/10/archive bytes=100- if-range \"e10\""), archiveRequests())
        assertContentEquals(original, folder.files[file("one", 1.0)])
        assertEquals(original.size.toLong(), indexed(10)!!.size)
    }

    @Test fun aPartAlreadyCompleteGoesStraightToTheCheck() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        val original = archives.getValue(10).first
        folder.files[file("one", 1.0) + ".part"] = original
        store.savePartEtag(10, "\"e10\"")
        val report = runner().run()
        assertNull(report.problem)
        assertContentEquals(original, folder.files[file("one", 1.0)])
        assertEquals("\"e10\"", indexed(10)!!.etag)
    }

    @Test fun aTruncatedArchiveIsNeverIndexed() = runTest {
        addSeries(1, "one", downloaded(10, 1.0), downloaded(11, 2.0))
        serve(10, text = "BAD ".repeat(30)); serve(11)
        store.mark(1, "one")
        val report = runner().run()
        assertNull(indexed(10))
        assertFalse(file("one", 1.0) + ".part" in folder.files)
        assertFalse(file("one", 1.0) in folder.files)
        assertTrue(indexed(11) != null)
        assertEquals(mapOf(1L to listOf(2.0)), report.imported)
        assertEquals(1, report.pending)
        assertNull(report.problem)
    }

    @Test fun threeUnreadableArchivesStopTheRun() = runTest {
        addSeries(1, "one", downloaded(10, 1.0), downloaded(11, 2.0), downloaded(12, 3.0), downloaded(13, 4.0))
        listOf(10L, 11L, 12L).forEach { serve(it, text = "BAD ".repeat(30)) }
        serve(13)
        store.mark(1, "one")
        val report = runner().run()
        val message = "Some chapters on the server could not be read; they will be tried again later"
        assertEquals(message, report.problem)
        assertEquals(message, store.problem().first())
        assertEquals(3, archiveRequests().size)
        assertNull(indexed(13))
        assertEquals(4, report.pending)
    }

    @Test fun aRemovedFolderStopsWithTheBanner() = runTest {
        addSeries(1, "one", downloaded(10, 1.0), downloaded(11, 2.0))
        serve(10); serve(11)
        store.mark(1, "one")
        folder.available = false
        val report = runner().run()
        val message = "SD card or folder not available: pick the folder again in Settings"
        assertEquals(message, report.problem)
        assertEquals(message, store.problem().first())
        assertNull(indexed(10))
        assertNull(indexed(11))
        assertTrue(archiveRequests().size <= 1)
    }

    @Test fun aFullDeviceStopsOnceAndRemovesThePart() = runTest {
        addSeries(1, "one", downloaded(10, 1.0), downloaded(11, 2.0))
        serve(10); serve(11)
        store.mark(1, "one")
        folder.failNextWriteWith = DeviceFull()
        val report = runner().run()
        val message = "Device full: free some space or delete read chapters"
        assertEquals(message, report.problem)
        assertEquals(message, store.problem().first())
        assertEquals(1, archiveRequests().size)
        assertTrue(folder.files.isEmpty())
        assertNull(indexed(10))
    }

    @Test fun aLostServerKeepsThePartForNextTime() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        val part = file("one", 1.0) + ".part"
        folder.files[part] = archives.getValue(10).first.copyOfRange(0, 100)
        store.savePartEtag(10, "\"e10\"")
        archiveStatus = HttpStatusCode.BadGateway
        val report = runner().run()
        val message = "Lost the server while copying; will continue next time"
        assertEquals(message, report.problem)
        assertEquals(message, store.problem().first())
        assertEquals(100, folder.files[part]?.size)
        assertEquals(1, report.pending)
    }

    @Test fun aFileAlreadyInTheFolderIsNeverReplaced() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        // Not indexed, and not the server's archive: someone else's file.
        folder.files[file("one", 1.0)] = "PK something else".encodeToByteArray()
        val report = runner().run()
        assertContentEquals("PK something else".encodeToByteArray(), folder.files[file("one", 1.0)])
        assertNull(indexed(10))
        assertEquals(1, report.pending)
        assertFalse(archiveRequests().any { !it.contains("bytes=") })
    }

    @Test fun theSameArchiveAlreadyInTheFolderIsAdopted() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        val original = archives.getValue(10).first
        folder.files[file("one", 1.0)] = original
        val report = runner().run()
        assertEquals("\"e10\"", indexed(10)!!.etag)
        assertContentEquals(original, folder.files[file("one", 1.0)])
        assertTrue(report.imported.isEmpty())
        assertEquals(0, report.pending)
    }

    @Test fun theBudgetStopsNewChapters() = runTest {
        addSeries(1, "one", *(1..5).map { downloaded(10L + it, it.toDouble()) }.toTypedArray())
        (11L..15L).forEach { serve(it) }
        store.mark(1, "one")
        copyTime = 20.minutes
        val report = runner().run(budget = 45.minutes)
        assertEquals(listOf(1.0, 2.0, 3.0), report.imported[1L])
        assertEquals(2, report.pending)
        assertNull(report.problem)
    }

    @Test fun aCleanRunClearsAnOldProblem() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        store.setProblem("Device full: free some space or delete read chapters")
        val report = runner().run()
        assertNull(report.problem)
        assertNull(store.problem().first())
    }

    @Test fun theOutboxDrainsBeforeCopying() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        Outbox(store, clock).position(1, 10, 4)
        runner().run()
        assertEquals(
            listOf(
                "identity",
                "PUT /api/reader/series/1/position",
                "GET /api/series",
                "GET /api/series/1",
                "GET /api/chapters/10/archive",
            ),
            log,
        )
        assertTrue(store.outbox().isEmpty())
    }

    @Test fun oldestChaptersFirst() = runTest {
        addSeries(1, "one", downloaded(13, 3.0), downloaded(11, 1.0), downloaded(12, 2.5))
        (11L..13L).forEach { serve(it) }
        store.mark(1, "one")
        val progress = mutableListOf<Pair<Int, Int>>()
        val report = runner().run { done, total -> progress += done to total }
        assertEquals(
            listOf("GET /api/chapters/11/archive", "GET /api/chapters/12/archive", "GET /api/chapters/13/archive"),
            archiveRequests(),
        )
        assertEquals(listOf(1.0, 2.5, 3.0), report.imported[1L])
        assertEquals(listOf(0 to 3, 1 to 3, 2 to 3, 3 to 3), progress)
    }

    @Test fun aPartFromAnOlderArchiveStartsOver() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10, text = "PK version A ".repeat(30), etag = "\"A\"")
        store.mark(1, "one")
        folder.files[file("one", 1.0) + ".part"] = archives.getValue(10).first.copyOfRange(0, 100)
        store.savePartEtag(10, "\"A\"")
        serve(10, text = "PK version B, rebuilt ".repeat(30), etag = "\"B\"")
        val report = runner().run()
        assertNull(report.problem)
        assertEquals(listOf("GET /api/chapters/10/archive bytes=100- if-range \"A\""), archiveRequests())
        assertContentEquals(archives.getValue(10).first, folder.files[file("one", 1.0)])
        assertEquals("\"B\"", indexed(10)!!.etag)
        assertNull(store.partEtag(10))
    }

    @Test fun aPartWithNoRecordedEtagStartsOver() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        folder.files[file("one", 1.0) + ".part"] = "PK from who knows where".encodeToByteArray()
        runner().run()
        assertEquals(listOf("GET /api/chapters/10/archive"), archiveRequests())
        assertContentEquals(archives.getValue(10).first, folder.files[file("one", 1.0)])
    }

    @Test fun aChapterMissingOnTheServerIsSkipped() = runTest {
        addSeries(1, "one", downloaded(10, 1.0), downloaded(11, 2.0))
        serve(11)
        store.mark(1, "one")
        val report = runner().run()
        assertNull(report.problem)
        assertNull(store.problem().first())
        assertNull(indexed(10))
        assertTrue(indexed(11) != null)
        assertEquals(1, report.pending)
    }

    @Test fun aBodyShorterThanDeclaredIsNeverIndexed() = runTest {
        addSeries(1, "one", downloaded(10, 1.0))
        serve(10)
        store.mark(1, "one")
        val delivered = archives.getValue(10).first.size
        declaredLength = delivered + 1_000L
        val report = runner().run()
        assertEquals("Lost the server while copying; will continue next time", report.problem)
        assertNull(indexed(10))
        assertFalse(file("one", 1.0) in folder.files)
        assertEquals(delivered, folder.files[file("one", 1.0) + ".part"]?.size)
    }

    @Test fun aFolderGoneMidRunStopsWithTheBanner() = runTest {
        for (failure in listOf<Exception>(ChapterFileMissing(), okio.IOException("No such device"))) {
            tearDown(); setUp(); log.clear(); series.clear(); chapters.clear(); archives.clear()
            addSeries(1, "one", downloaded(10, 1.0), downloaded(11, 2.0), downloaded(12, 3.0))
            (10L..12L).forEach { serve(it) }
            store.mark(1, "one")
            onArchive = { id -> if (id == 11L) folder.goneWith = failure }
            val report = runner().run()
            val message = "SD card or folder not available: pick the folder again in Settings"
            assertEquals(message, report.problem, "after $failure")
            assertEquals(message, store.problem().first())
            assertTrue(indexed(10) != null)
            assertNull(indexed(11))
            assertNull(indexed(12))
            assertEquals(setOf(file("one", 1.0)), folder.files.keys)
        }
    }
}
