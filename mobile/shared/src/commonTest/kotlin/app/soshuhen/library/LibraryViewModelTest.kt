package app.soshuhen.library

import app.soshuhen.api.Fixtures
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.LocalStore
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

@OptIn(ExperimentalCoroutinesApi::class)
class LibraryViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore

    @BeforeTest fun setUp() {
        Dispatchers.setMain(dispatcher)
        db = testDatabase(dispatcher)
        store = LocalStore(db)
    }

    @AfterTest fun tearDown() {
        Dispatchers.resetMain()
        db.close()
    }

    /** Answers in turn: true is the fixture library, false is a 500. */
    private fun api(vararg replies: Boolean): SoshuhenApi {
        var call = 0
        // On the test dispatcher: on Ktor's own, the request would run in real
        // time while the client's timeout ran in virtual time and won.
        val engine = MockEngine(
            MockEngineConfig().apply {
                dispatcher = this@LibraryViewModelTest.dispatcher
                addHandler {
                    val ok = replies[minOf(call++, replies.size - 1)]
                    if (ok) respond(Fixtures.SERIES, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json"))
                    else respondError(HttpStatusCode.InternalServerError)
                }
            },
        )
        return SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
    }

    @Test fun firstLoadFailureIsFailed() = runTest(dispatcher) {
        val vm = LibraryViewModel(MutableStateFlow(api(false)), store)
        advanceUntilIdle()
        assertIs<LoadState.Failed>(vm.state.value)
    }

    @Test fun loadsTheLibrary() = runTest(dispatcher) {
        val vm = LibraryViewModel(MutableStateFlow(api(true)), store)
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<List<app.soshuhen.api.Series>>>(vm.state.value)
        // The fixture's second row is prose, which the app does not show.
        assertEquals(listOf(243L), state.data.map { it.id })
        assertNull(state.refreshFailed)
    }

    @Test fun refreshFailureKeepsTheLoadedRows() = runTest(dispatcher) {
        val vm = LibraryViewModel(MutableStateFlow(api(true, false)), store)
        advanceUntilIdle()
        vm.refresh()
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<List<app.soshuhen.api.Series>>>(vm.state.value)
        // The fixture's second row is prose, which the app does not show.
        assertEquals(listOf(243L), state.data.map { it.id })
        assertNotNull(state.refreshFailed)
    }

    @Test fun noServerYetIsLoading() = runTest(dispatcher) {
        val vm = LibraryViewModel(MutableStateFlow(null), store)
        advanceUntilIdle()
        assertIs<LoadState.Loading>(vm.state.value)
    }

    @Test fun aServerFoundAtANewAddressReloadsByItself() = runTest(dispatcher) {
        val api = MutableStateFlow<SoshuhenApi?>(api(false))
        val vm = LibraryViewModel(api, store)
        advanceUntilIdle()
        assertIs<LoadState.Failed>(vm.state.value)
        api.value = api(true)
        advanceUntilIdle()
        assertIs<LoadState.Loaded<List<app.soshuhen.api.Series>>>(vm.state.value)
    }

    @Test fun offlineWithASnapshotShowsTheSnapshot() = runTest(dispatcher) {
        store.saveSeries(Fixtures.SERIES)
        val vm = LibraryViewModel(MutableStateFlow(api(false)), store)
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<List<app.soshuhen.api.Series>>>(vm.state.value)
        assertEquals(listOf(243L), state.data.map { it.id })
        assertEquals(OFFLINE, state.refreshFailed)
    }

    @Test fun offlineWithoutASnapshotIsFailed() = runTest(dispatcher) {
        val vm = LibraryViewModel(MutableStateFlow(api(false)), store)
        advanceUntilIdle()
        assertIs<LoadState.Failed>(vm.state.value)
    }

    @Test fun aSuccessfulLoadSavesTheSnapshot() = runTest(dispatcher) {
        LibraryViewModel(MutableStateFlow(api(true)), store)
        advanceUntilIdle()
        assertEquals(2, store.seriesSnapshot()!!.size)
    }
}
