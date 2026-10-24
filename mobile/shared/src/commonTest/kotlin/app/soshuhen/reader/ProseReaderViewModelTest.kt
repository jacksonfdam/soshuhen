package app.soshuhen.reader

import app.soshuhen.api.Fixtures
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.BookExtractor
import app.soshuhen.core.BookKind
import app.soshuhen.core.BookRef
import app.soshuhen.core.DeviceVolume
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
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okio.Path.Companion.toPath
import okio.Source
import okio.buffer
import okio.fakefilesystem.FakeFileSystem
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class ProseReaderViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private lateinit var outbox: Outbox
    private val folder = FakeChapterFolder()
    private val fs = FakeFileSystem()
    private val requests = mutableListOf<Pair<HttpMethod, String>>()
    private val unpacked = mutableListOf<Pair<BookRef, String>>()
    private val unpackedBytes = mutableListOf<String>()
    private var unpackFails: Exception? = null
    private var declaredLength: Long? = null
    private var dispatched = 0

    // Counts what the view model hands it, to show the heavy work leaves the main thread.
    private val io = object : kotlinx.coroutines.CoroutineDispatcher() {
        override fun dispatch(context: kotlin.coroutines.CoroutineContext, block: Runnable) {
            dispatched++
            dispatcher.dispatch(context, block)
        }
    }

    private val home = MutableStateFlow(false)
    private val api = MutableStateFlow<SoshuhenApi?>(null)

    // A real book tree in the fake file system; the fake extractor only says where it is.
    private val bookDir = "/cache/books/the-book".toPath()
    private val books = BookExtractor { ref, version, source: Source ->
        unpackFails?.let { throw it }
        unpacked += ref to version
        unpackedBytes += source.buffer().use { it.readUtf8() }
        bookDir
    }

    private fun writeBook() {
        fun write(name: String, text: String) {
            val path = bookDir / name
            fs.createDirectories(path.parent!!)
            fs.write(path) { writeUtf8(text) }
        }
        write("META-INF/container.xml", """<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>""")
        write(
            "OEBPS/content.opf",
            """<package><manifest><item id="c" href="c.xhtml"/></manifest><spine><itemref idref="c"/></spine></package>""",
        )
        write("OEBPS/c.xhtml", "<html><body><h2>One</h2><p>first paragraph</p><p>second paragraph</p></body></html>")
    }

    private val proseDetail = Fixtures.PROSE_DETAIL.replace(
        "\"volumes\": [",
        """"volumes": [
        {"id": 40, "number": 0.0, "edition": "light", "state": "downloaded", "file_path": "/manga/tsuki/v0.epub", "readable": true},""",
    ).replace(
        "\"readable\": true}\n      ],",
        """"readable": true},
        {"id": 42, "number": 2.0, "edition": "light", "state": "downloaded", "file_path": "/manga/tsuki/v2.epub", "readable": true}
      ],""",
    )

    @BeforeTest fun setUp() {
        Dispatchers.setMain(dispatcher)
        db = testDatabase(dispatcher)
        store = LocalStore(db)
        outbox = Outbox(store) { Instant.parse("2026-10-24T08:00:00Z") }
        api.value = SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine()))
        writeBook()
    }

    @AfterTest fun tearDown() {
        Dispatchers.resetMain()
        db.close()
    }

    private fun engine() = MockEngine(
        MockEngineConfig().apply {
            dispatcher = this@ProseReaderViewModelTest.dispatcher
            addHandler { request ->
                val path = request.url.encodedPath
                requests += request.method to path
                val json = headersOf(HttpHeaders.ContentType, "application/json")
                when {
                    path == "/api/series/308" -> respond(proseDetail, HttpStatusCode.OK, json)
                    path == "/api/volumes/42/archive" -> respond(
                        "PK server volume", HttpStatusCode.OK,
                        headersOf(
                            HttpHeaders.ETag to listOf("\"s42\""),
                            HttpHeaders.ContentLength to listOf("${declaredLength ?: 16}"),
                        ),
                    )
                    request.method != HttpMethod.Get -> respond("{}", HttpStatusCode.OK, json)
                    else -> respondError(HttpStatusCode.NotFound)
                }
            }
        },
    )

    private suspend fun volumeOnDevice(id: Long, number: Double, present: Boolean = true) {
        val name = "tsuki - Vol.$number.epub"
        val uri = if (present) folder.put("tsuki", name) else folder.uri("tsuki", name)
        store.indexVolume(DeviceVolume(id, 308, number, name, uri, "\"e$id\"", 3, Instant.parse("2026-10-20T00:00:00Z")))
    }

    private fun reader(ref: BookRef) =
        ProseReaderViewModel(308, ref, api, home, store, folder, books, outbox, "/cache".toPath(), fs, io)

    private fun ProseReaderViewModel.ui(): ProseUi = assertIs<ProseState.Ready>(state.value).ui

    private val volume41 = BookRef(BookKind.Volume, 41)

    @Test fun aDeviceVolumeOpensAtItsSavedPosition() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0)
        volumeOnDevice(40, 0.0)
        ProseStore(store).savePosition(volume41, ProsePosition(0, 2, 3))
        val vm = reader(volume41)
        advanceUntilIdle()
        val ui = vm.ui()
        assertEquals(ProsePosition(0, 2, 3), ui.position)
        assertEquals(3, ui.book.sections.single().size)
        assertEquals(listOf(volume41 to "\"e41\":3"), unpacked)
        assertEquals(BookRef(BookKind.Volume, 40), ui.previous)
        // Volume 2 is only on the server, and the phone is away.
        assertNull(ui.next)
        assertTrue(requests.isEmpty())
    }

    @Test fun atHomeAServerVolumeOpensWithoutTouchingTheFolder() = runTest(dispatcher) {
        home.value = true
        val vm = reader(BookRef(BookKind.Volume, 42))
        advanceUntilIdle()
        vm.ui()
        assertEquals(listOf("PK server volume"), unpackedBytes)
        assertEquals("server:\"s42\"", unpacked.single().second)
        assertTrue(folder.files.isEmpty())
        assertTrue(fs.list("/cache".toPath()).none { it.name.endsWith(".epub") }, "the download is removed once unpacked")
    }

    @Test fun awayFromHomeAServerVolumeIsUnavailable() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        val vm = reader(BookRef(BookKind.Volume, 42))
        advanceUntilIdle()
        assertEquals(
            "Not on this device. It will be copied the next time you are home.",
            assertIs<ProseState.Unavailable>(vm.state.value).message,
        )
    }

    @Test fun finishingAVolumeQueuesOneVolumeCompletion() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0)
        val vm = reader(volume41)
        advanceUntilIdle()
        vm.finish()
        vm.finish()
        advanceUntilIdle()
        val queued = store.outbox().filter { it.kind == "volume_complete" }
        assertEquals(listOf(41L), queued.map { it.chapterId })
        assertEquals(1, store.volumeProgress(308))
    }

    @Test fun atHomeAFinishedVolumeIsSentAtOnce() = runTest(dispatcher) {
        home.value = true
        volumeOnDevice(41, 1.0)
        val vm = reader(volume41)
        advanceUntilIdle()
        vm.finish()
        advanceUntilIdle()
        assertTrue(HttpMethod.Post to "/api/reader/volumes/41/complete" in requests)
        assertTrue(store.outbox().isEmpty())
    }

    @Test fun positionIsSavedAfterTheDebounce() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0)
        val vm = reader(volume41)
        advanceUntilIdle()
        vm.moveTo(ProsePosition(0, 1, 4))
        vm.moveTo(ProsePosition(0, 2, 0))
        advanceTimeBy(500)
        assertNull(ProseStore(store).position(volume41))
        advanceUntilIdle()
        assertEquals(ProsePosition(0, 2, 0), ProseStore(store).position(volume41))
        assertEquals(ProsePosition(0, 2, 0), vm.ui().position)
    }

    @Test fun styleIsForEveryBookAndDirectionIsPerSeries() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0)
        val vm = reader(volume41)
        advanceUntilIdle()
        assertEquals("paged_ltr", vm.ui().mode)
        vm.setMode("paged_rtl")
        vm.setStyle(ProseStyle(fontSize = 22, font = "sans", background = "sepia"))
        advanceUntilIdle()
        assertEquals("paged_rtl", ProseStore(store).mode(308))
        assertNull(ProseStore(store).mode(309))
        assertEquals(ProseStyle(22, "sans", "sepia"), ProseStore(store).style())
        assertEquals("paged_rtl", vm.ui().mode)
    }

    @Test fun aCorruptDeviceVolumeIsMarkedUnreadable() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0)
        unpackFails = IllegalStateException("bad zip")
        val vm = reader(volume41)
        advanceUntilIdle()
        assertEquals(
            "This chapter's file could not be read. It will be copied again at home.",
            assertIs<ProseState.Unavailable>(vm.state.value).message,
        )
        assertEquals("unreadable", store.deviceVolume(41)?.etag)
    }

    @Test fun aMissingDeviceFileIsForgotten() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0, present = false)
        val vm = reader(volume41)
        advanceUntilIdle()
        assertIs<ProseState.Unavailable>(vm.state.value)
        assertNull(store.deviceVolume(41))
    }

    @Test fun openingTheNextVolumeSavesThePlaceLeftBehind() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0)
        volumeOnDevice(40, 0.0)
        val vm = reader(volume41)
        advanceUntilIdle()
        vm.moveTo(ProsePosition(0, 1, 0))
        vm.open(BookRef(BookKind.Volume, 40))
        advanceUntilIdle()
        assertEquals(ProsePosition(0, 1, 0), ProseStore(store).position(volume41))
        assertEquals(BookRef(BookKind.Volume, 40), vm.ui().ref)
    }

    // A connection that closes cleanly mid-body looks like the end of the file;
    // unpacked, it would be a volume with its end missing and no error.
    @Test fun aCutOffServerDownloadIsNotOpened() = runTest(dispatcher) {
        home.value = true
        declaredLength = 4000
        val vm = reader(BookRef(BookKind.Volume, 42))
        advanceUntilIdle()
        assertEquals("The server could not open this chapter.", assertIs<ProseState.Unavailable>(vm.state.value).message)
        assertTrue(unpacked.isEmpty())
    }

    @Test fun theBookIsReadOffTheMainThread() = runTest(dispatcher) {
        store.saveDetail(308, proseDetail)
        volumeOnDevice(41, 1.0)
        val vm = reader(volume41)
        advanceUntilIdle()
        vm.ui()
        assertTrue(dispatched > 0)
    }
}
