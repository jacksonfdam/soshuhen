package app.soshuhen.reader

import app.soshuhen.core.PageExtractor
import app.soshuhen.api.Fixtures
import app.soshuhen.api.ReaderPrefs
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.DeviceChapter
import app.soshuhen.core.FakeChapterFolder
import app.soshuhen.core.LocalStore
import app.soshuhen.core.Outbox
import app.soshuhen.core.testDatabase
import app.soshuhen.db.SoshuhenDatabase
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okio.Path
import okio.Path.Companion.toPath
import okio.Source
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class ReaderViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private lateinit var outbox: Outbox
    private val folder = FakeChapterFolder()
    private val requests = mutableListOf<Pair<HttpMethod, String>>()
    private val extracted = mutableListOf<Long>()

    private val home = MutableStateFlow(false)
    private val api = MutableStateFlow<SoshuhenApi?>(null)

    private fun pagesOf(count: Int): List<Path> = List(count) { "/cache/reader/$it.jpg".toPath() }

    private var devicePages = 5
    private var extractFails: Exception? = null

    // Never reads the source, as ZipPages does not when the chapter is already
    // in its cache: closing it is the caller's job either way.
    private val extractor = PageExtractor { chapterId, _, _: Source ->
        extractFails?.let { throw it }
        extracted += chapterId
        pagesOf(devicePages)
    }

    @BeforeTest fun setUp() {
        Dispatchers.setMain(dispatcher)
        db = testDatabase(dispatcher)
        store = LocalStore(db)
        outbox = Outbox(store) { Instant.parse("2026-10-21T08:10:00Z") }
        api.value = SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine()))
    }

    @AfterTest fun tearDown() {
        Dispatchers.resetMain()
        db.close()
    }

    private fun engine() = MockEngine(
        MockEngineConfig().apply {
            dispatcher = this@ReaderViewModelTest.dispatcher
            addHandler { request ->
                val path = request.url.encodedPath
                requests += request.method to path
                val json = headersOf(HttpHeaders.ContentType, "application/json")
                when {
                    path == "/api/series/1" -> respond(Fixtures.DETAIL, HttpStatusCode.OK, json)
                    path == "/api/reader/chapters/13" ->
                        respond("""{"page_count": 7, "position": 2}""", HttpStatusCode.OK, json)
                    path == "/api/reader/series/1/prefs" && request.method == HttpMethod.Get ->
                        respond(
                            """{"mode": "long_strip", "scale": "fit_width", "background": "white", "custom": true}""",
                            HttpStatusCode.OK, json,
                        )
                    request.method != HttpMethod.Get -> respond("{}", HttpStatusCode.OK, json)
                    else -> respondError(HttpStatusCode.NotFound)
                }
            }
        },
    )

    private suspend fun onDevice(chapterId: Long, number: Double, present: Boolean = true) {
        val name = "frieren - Ch.$number.cbz"
        val uri = if (present) folder.put("frieren", name) else folder.uri("frieren", name)
        store.indexChapter(
            DeviceChapter(chapterId, 1, number, name, uri, "\"e\"", 3, Instant.parse("2026-10-20T00:00:00Z")),
        )
    }

    private fun reader(chapterId: Long, startPage: Int? = null, outbox: Outbox = this.outbox) =
        ReaderViewModel(1, chapterId, startPage, api, home, store, folder, extractor, outbox)

    private fun ReaderViewModel.ui(): ReaderUi = assertIs<ReaderState.Ready>(state.value).ui

    private suspend fun queued(kind: String) = store.outbox().filter { it.kind == kind }

    @Test fun aDeviceChapterOpensFromTheDevice() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        val ui = vm.ui()
        assertEquals(PageSource.Device(pagesOf(5)), ui.source)
        assertEquals(5, ui.pageCount)
        assertEquals(0, ui.page)
        assertEquals(11L, ui.chapter.id)
        assertEquals(listOf(11L), extracted)
    }

    @Test fun aHalfReadDeviceChapterReopensWhereReadingStopped() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        outbox.position(1, 11, 3)
        val vm = reader(11)
        advanceUntilIdle()
        assertEquals(3, vm.ui().page)
    }

    @Test fun aDeviceChapterReopensAtTheServersLastKnownPlace() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        store.saveResume(1, app.soshuhen.api.Resume(11, 2))
        onDevice(11, 1.0)
        onDevice(13, 2.5)
        val vm = reader(11)
        advanceUntilIdle()
        assertEquals(2, vm.ui().page)
        // Another chapter's place is not this one's.
        val other = reader(13)
        advanceUntilIdle()
        assertEquals(0, other.ui().page)
    }

    @Test fun awayFromHomeAChapterNotOnTheDeviceIsUnavailable() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        val vm = reader(13)
        advanceUntilIdle()
        val state = vm.state.value
        assertEquals(
            "Not on this device. It will be copied the next time you are home.",
            (state as ReaderState.Unavailable).message,
        )
        assertTrue(requests.isEmpty())
    }

    @Test fun atHomeAnOnServerChapterStreamsFromTheServer() = runTest(dispatcher) {
        home.value = true
        val vm = reader(13)
        advanceUntilIdle()
        val ui = vm.ui()
        assertEquals(PageSource.Server(api.value!!, 13, 7), ui.source)
        assertEquals(7, ui.pageCount)
        // No page asked for: the server's saved position is where reading resumes.
        assertEquals(2, ui.page)
        assertEquals(11L, ui.previous)
        assertNull(ui.next)
    }

    @Test fun atHomeANotDownloadedChapterIsUnavailable() = runTest(dispatcher) {
        home.value = true
        val vm = reader(12)
        advanceUntilIdle()
        assertEquals("Not downloaded on the server yet.", assertIs<ReaderState.Unavailable>(vm.state.value).message)
        // Asking for its manifest would make the server fetch it from the source.
        assertFalse(requests.any { it.second.startsWith("/api/reader/chapters/12") })
    }

    @Test fun aMissingFileIsUnavailableAndForgotten() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0, present = false)
        val vm = reader(11)
        advanceUntilIdle()
        assertEquals(
            "This chapter's file is missing from the folder. It will be copied again at home.",
            assertIs<ReaderState.Unavailable>(vm.state.value).message,
        )
        assertNull(store.deviceChapter(11))
    }

    @Test fun pageChangesQueueOnePositionPerSecond() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        vm.goTo(1)
        advanceTimeBy(200)
        vm.goTo(2)
        advanceTimeBy(200)
        vm.goTo(3)
        advanceTimeBy(900)
        runCurrent()
        assertTrue(queued("position").isEmpty())
        advanceTimeBy(200)
        runCurrent()
        val positions = queued("position")
        assertEquals(1, positions.size)
        assertEquals(3, positions.single().page)
        assertEquals(11L, positions.single().chapterId)
        assertEquals(3, vm.ui().page)
    }

    @Test fun theLastPageCompletesOnce() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        vm.goTo(3)
        advanceUntilIdle()
        assertTrue(queued("complete").isEmpty())
        vm.goTo(4)
        advanceUntilIdle()
        vm.goTo(3)
        vm.goTo(4)
        vm.nextPage()
        advanceUntilIdle()
        assertEquals(listOf(11L), queued("complete").map { it.chapterId })
    }

    @Test fun theLastSpreadCompletesInDoubleMode() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        store.savePrefs(1, ReaderPrefs("double", "fit_screen", "black"))
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        // Spreads of five pages: [0], [1, 2], [3, 4].
        vm.nextPage()
        assertEquals(1, vm.ui().page)
        vm.nextPage()
        assertEquals(3, vm.ui().page)
        advanceUntilIdle()
        assertEquals(1, queued("complete").size)
        vm.previousPage()
        assertEquals(1, vm.ui().page)
    }

    @Test fun completingRaisesLocalProgress() = runTest(dispatcher) {
        store.saveSeries("""[{"id": 1, "title": "Frieren", "slug": "frieren", "progress": 1, "extra": "kept"},
            {"id": 2, "title": "Other", "slug": "other", "progress": 0}]""")
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(13, 2.5)
        val vm = reader(13)
        advanceUntilIdle()
        vm.goTo(4)
        advanceUntilIdle()
        // Lists count whole chapters: finishing 2.5 means chapter 2 is read.
        assertEquals(2, store.seriesSnapshot()!!.single { it.id == 1L }.progress)
        assertEquals(0, store.seriesSnapshot()!!.single { it.id == 2L }.progress)
        assertEquals(2, store.detailSnapshot(1)!!.series.progress)
    }

    @Test fun completingAnEarlierChapterNeverLowersLocalProgress() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL.replace("\"progress\": 1", "\"progress\": 5"))
        onDevice(13, 2.5)
        val vm = reader(13)
        advanceUntilIdle()
        vm.goTo(4)
        advanceUntilIdle()
        assertEquals(5, store.detailSnapshot(1)!!.series.progress)
    }

    @Test fun prefsFallBackToSnapshotThenDefaults() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val first = reader(11)
        advanceUntilIdle()
        assertEquals(ReaderPrefs("paged_rtl", "fit_screen", "black"), first.ui().prefs)

        store.savePrefs(1, ReaderPrefs("paged_ltr", "fit_width", "gray", custom = true))
        val second = reader(11)
        advanceUntilIdle()
        assertEquals(ReaderPrefs("paged_ltr", "fit_width", "gray", custom = true), second.ui().prefs)
    }

    @Test fun atHomePrefsComeFromTheServerAndAreKept() = runTest(dispatcher) {
        home.value = true
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        val server = ReaderPrefs("long_strip", "fit_width", "white", custom = true)
        assertEquals(server, vm.ui().prefs)
        assertEquals(server, store.prefsSnapshot(1))
    }

    @Test fun setPrefsKeepsThemAndQueuesThemForTheServer() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        val chosen = ReaderPrefs("double", "fit_height", "gray")
        vm.setPrefs(chosen)
        assertEquals(chosen, vm.ui().prefs)
        advanceUntilIdle()
        assertEquals(chosen, store.prefsSnapshot(1))
        assertEquals(1, queued("prefs").size)
    }

    @Test fun atHomeQueuedEventsAreSentAtOnce() = runTest(dispatcher) {
        home.value = true
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        vm.goTo(4)
        advanceUntilIdle()
        assertTrue(store.outbox().isEmpty())
        assertTrue(requests.contains(HttpMethod.Put to "/api/reader/series/1/position"))
        assertTrue(requests.contains(HttpMethod.Post to "/api/reader/chapters/11/complete"))
    }

    @Test fun nextAwayFromHomeSkipsChaptersNotOnTheDevice() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val away = reader(11)
        advanceUntilIdle()
        // 13 is on the server, which is out of reach away from home.
        assertNull(away.ui().next)

        home.value = true
        val atHome = reader(11)
        advanceUntilIdle()
        assertEquals(13L, atHome.ui().next)
        assertNull(atHome.ui().previous)
    }

    @Test fun openChapterMovesToItFromTheFirstPage() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        onDevice(13, 2.5)
        val vm = reader(11, startPage = 3)
        advanceUntilIdle()
        assertEquals(3, vm.ui().page)
        assertEquals(13L, vm.ui().next)
        vm.goTo(4)
        advanceUntilIdle()
        vm.openChapter(13)
        advanceUntilIdle()
        val ui = vm.ui()
        assertEquals(13L, ui.chapter.id)
        assertEquals(0, ui.page)
        assertEquals(11L, ui.previous)
        // Completion is once per open: the new chapter can be finished too.
        vm.goTo(4)
        advanceUntilIdle()
        assertEquals(listOf(11L, 13L), queued("complete").map { it.chapterId })
    }

    @Test fun toggleChromeFlipsVisibility() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val vm = reader(11)
        advanceUntilIdle()
        assertTrue(vm.ui().chromeVisible)
        vm.toggleChrome()
        assertFalse(vm.ui().chromeVisible)
    }

    @Test fun keysReachOnlyAReaderThatIsListening() = runTest(dispatcher) {
        assertFalse(ReaderKeys.emit(ReaderKey.Next))
        val got = mutableListOf<ReaderKey>()
        val job = launch { ReaderKeys.events.collect { got += it } }
        runCurrent()
        assertTrue(ReaderKeys.emit(ReaderKey.Previous))
        runCurrent()
        assertEquals(listOf(ReaderKey.Previous), got)
        job.cancel()
        runCurrent()
        assertFalse(ReaderKeys.emit(ReaderKey.Next))
    }

    @Test fun awayFromHomeANotDownloadedChapterSaysSo() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        val vm = reader(12)
        advanceUntilIdle()
        // Not "copied the next time you are home": only a chapter the server
        // holds as a file is ever copied.
        assertEquals("Not downloaded on the server yet.", assertIs<ReaderState.Unavailable>(vm.state.value).message)
    }

    @Test fun everySourceOpenedFromTheFolderIsClosed() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        reader(11)
        advanceUntilIdle()
        reader(11)
        advanceUntilIdle()
        assertEquals(2, folder.opened.size)
        assertTrue(folder.opened.all { it.closed })
    }

    @Test fun anUnreadableArchiveIsUnavailableAndForgotten() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        extractFails = okio.IOException("invalid zip")
        val vm = reader(11)
        advanceUntilIdle()
        assertEquals(
            "This chapter's file could not be read. It will be copied again at home.",
            assertIs<ReaderState.Unavailable>(vm.state.value).message,
        )
        assertNull(store.deviceChapter(11))
        assertTrue(folder.opened.all { it.closed })
    }

    @Test fun aFailedOutboxWriteLosesThatEventOnly() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        onDevice(11, 1.0)
        val vm = reader(11, outbox = Outbox(QueueFailingStore(db)) { Instant.parse("2026-10-21T08:10:00Z") })
        advanceUntilIdle()
        vm.goTo(4)
        vm.setPrefs(ReaderPrefs("double", "fit_height", "gray"))
        advanceUntilIdle()
        vm.goTo(2)
        assertEquals(2, vm.ui().page)
        assertEquals(ReaderPrefs("double", "fit_height", "gray"), store.prefsSnapshot(1))
    }

    private class QueueFailingStore(db: SoshuhenDatabase) : LocalStore(db) {
        override suspend fun enqueue(entry: app.soshuhen.db.OutboxEntity) = error("disk full")
    }
}
