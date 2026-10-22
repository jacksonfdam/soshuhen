package app.soshuhen.detail

import app.soshuhen.api.Fixtures
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.FailingStore
import app.soshuhen.core.DeviceLibrary
import app.soshuhen.core.FakeChapterFolder
import app.soshuhen.core.LocalStore
import app.soshuhen.core.Outbox
import app.soshuhen.core.testDatabase
import app.soshuhen.db.SoshuhenDatabase
import app.soshuhen.ui.OFFLINE
import app.soshuhen.ui.LoadState
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class SeriesDetailViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private val home = MutableStateFlow(true)

    @BeforeTest fun setUp() {
        Dispatchers.setMain(dispatcher)
        db = testDatabase(dispatcher)
        store = LocalStore(db)
    }

    @AfterTest fun tearDown() {
        Dispatchers.resetMain()
        db.close()
    }

    private fun api(
        resume: () -> HttpStatusCode = { HttpStatusCode.NotFound },
        resumeBody: String = "",
        detailOk: () -> Boolean,
    ): SoshuhenApi {
        val json = headersOf(HttpHeaders.ContentType, "application/json")
        val engine = MockEngine(
            MockEngineConfig().apply {
                dispatcher = this@SeriesDetailViewModelTest.dispatcher
                addHandler { request ->
                    when {
                        request.url.encodedPath.endsWith("/resume") -> resume().let { status ->
                            if (status == HttpStatusCode.OK) respond(resumeBody, status, json) else respondError(status)
                        }
                        detailOk() -> respond(Fixtures.DETAIL, HttpStatusCode.OK, json)
                        else -> respondError(HttpStatusCode.InternalServerError)
                    }
                }
            },
        )
        return SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
    }

    @Test fun loadsRowsAndWhatToContinue() = runTest(dispatcher) {
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { true }), home, store, DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        val ui = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value).data
        assertEquals(listOf(2.5, 2.0, 1.0), ui.rows.map { it.number })
        assertEquals(13L, ui.continueWith?.id)
    }

    @Test fun detailRefreshFailureKeepsLoadedRows() = runTest(dispatcher) {
        var ok = true
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { ok }), home, store, DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        ok = false
        vm.refresh()
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value)
        assertEquals(3, state.data.rows.size)
        assertNotNull(state.refreshFailed)
    }

    @Test fun aServerFoundAtANewAddressReloadsByItself() = runTest(dispatcher) {
        val api = MutableStateFlow<SoshuhenApi?>(api { false })
        val vm = SeriesDetailViewModel(1, api, home, store, DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        assertIs<LoadState.Failed>(vm.state.value)
        api.value = api { true }
        advanceUntilIdle()
        assertIs<LoadState.Loaded<DetailUi>>(vm.state.value)
    }

    @Test fun detailOfflineShowsTheSnapshot() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { false }), home, store, DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value)
        assertEquals(3, state.data.rows.size)
        assertEquals(OFFLINE, state.refreshFailed)
    }
    @Test fun aFailedSaveDoesNotChangeWhatIsShown() = runTest(dispatcher) {
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { true }), home, FailingStore(db), DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value)
        assertEquals(3, state.data.rows.size)
        assertNull(state.refreshFailed)
    }

    @Test fun offlineContinueKeepsTheServersResumePoint() = runTest(dispatcher) {
        val online = SeriesDetailViewModel(
            1, MutableStateFlow(api({ HttpStatusCode.OK }, """{"chapter_id": 11, "page": 4}""") { true }),
            home, store, DeviceLibrary(store, FakeChapterFolder()),
        )
        advanceUntilIdle()
        assertEquals(11L, assertIs<LoadState.Loaded<DetailUi>>(online.state.value).data.continueWith?.id)

        val offline = SeriesDetailViewModel(1, MutableStateFlow(api { false }), home, store, DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        val ui = assertIs<LoadState.Loaded<DetailUi>>(offline.state.value).data
        assertEquals(11L, ui.continueWith?.id)
        assertEquals(4, ui.continuePage)
    }

    @Test fun offlineContinueFollowsReadingQueuedOnTheDevice() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        Outbox(store) { Instant.parse("2026-10-21T08:10:00Z") }.position(1, 11, 2)
        Outbox(store) { Instant.parse("2026-10-21T08:11:00Z") }.position(1, 13, 6)
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { false }), home, store, DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        val ui = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value).data
        assertEquals(13L, ui.continueWith?.id)
        assertEquals(6, ui.continuePage)
    }

    @Test fun aFailedResumeKeepsTheDetailThatLoaded() = runTest(dispatcher) {
        val vm = SeriesDetailViewModel(
            1, MutableStateFlow(api({ HttpStatusCode.InternalServerError }) { true }),
            home, store, DeviceLibrary(store, FakeChapterFolder()),
        )
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value)
        assertNull(state.refreshFailed)
        assertEquals(13L, state.data.continueWith?.id)
        assertNotNull(store.detailSnapshot(1))
    }

    @Test fun aRefreshThatFailsAwayFromHomeSaysOffline() = runTest(dispatcher) {
        var ok = true
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { ok }), home, store, DeviceLibrary(store, FakeChapterFolder()))
        advanceUntilIdle()
        ok = false
        home.value = false
        vm.refresh()
        advanceUntilIdle()
        assertEquals(OFFLINE, assertIs<LoadState.Loaded<DetailUi>>(vm.state.value).refreshFailed)
    }
}
