package app.soshuhen.detail

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

@OptIn(ExperimentalCoroutinesApi::class)
class SeriesDetailViewModelTest {
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

    private fun api(detailOk: () -> Boolean): SoshuhenApi {
        val json = headersOf(HttpHeaders.ContentType, "application/json")
        val engine = MockEngine(
            MockEngineConfig().apply {
                dispatcher = this@SeriesDetailViewModelTest.dispatcher
                addHandler { request ->
                    when {
                        request.url.encodedPath.endsWith("/resume") -> respondError(HttpStatusCode.NotFound)
                        detailOk() -> respond(Fixtures.DETAIL, HttpStatusCode.OK, json)
                        else -> respondError(HttpStatusCode.InternalServerError)
                    }
                }
            },
        )
        return SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
    }

    @Test fun loadsRowsAndWhatToContinue() = runTest(dispatcher) {
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { true }), store)
        advanceUntilIdle()
        val ui = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value).data
        assertEquals(listOf(2.5, 2.0, 1.0), ui.rows.map { it.number })
        assertEquals(13L, ui.continueWith?.id)
    }

    @Test fun detailRefreshFailureKeepsLoadedRows() = runTest(dispatcher) {
        var ok = true
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { ok }), store)
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
        val vm = SeriesDetailViewModel(1, api, store)
        advanceUntilIdle()
        assertIs<LoadState.Failed>(vm.state.value)
        api.value = api { true }
        advanceUntilIdle()
        assertIs<LoadState.Loaded<DetailUi>>(vm.state.value)
    }

    @Test fun detailOfflineShowsTheSnapshot() = runTest(dispatcher) {
        store.saveDetail(1, Fixtures.DETAIL)
        val vm = SeriesDetailViewModel(1, MutableStateFlow(api { false }), store)
        advanceUntilIdle()
        val state = assertIs<LoadState.Loaded<DetailUi>>(vm.state.value)
        assertEquals(3, state.data.rows.size)
        assertEquals(OFFLINE, state.refreshFailed)
    }
}
