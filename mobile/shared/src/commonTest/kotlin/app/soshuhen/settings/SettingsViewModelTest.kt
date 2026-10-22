package app.soshuhen.settings

import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.FakeServerStore
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respondError
import io.ktor.http.HttpStatusCode
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

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @BeforeTest fun setUp() = Dispatchers.setMain(dispatcher)
    @AfterTest fun tearDown() = Dispatchers.resetMain()

    private fun api(base: String) = SoshuhenApi(
        base,
        soshuhenHttpClient(
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@SettingsViewModelTest.dispatcher
                    addHandler { respondError(HttpStatusCode.InternalServerError) }
                },
            ),
        ),
    )

    @Test fun theCardFollowsTheServerToItsNewAddress() = runTest(dispatcher) {
        val api = MutableStateFlow<SoshuhenApi?>(api("http://10.0.0.20:8080"))
        val vm = SettingsViewModel(api, FakeServerStore())
        advanceUntilIdle()
        api.value = api("http://10.0.0.31:8080")
        advanceUntilIdle()
        assertEquals("http://10.0.0.31:8080", vm.server.value?.baseUrl)
    }

    @Test fun volumeKeysTurnPagesUntilSwitchedOff() = runTest(dispatcher) {
        val store = FakeServerStore()
        val vm = SettingsViewModel(MutableStateFlow(null), store)
        advanceUntilIdle()
        assertEquals(true, vm.volumeKeys.value)
        assertEquals(false, vm.volumeInvert.value)
        vm.setVolumeKeys(false)
        vm.setVolumeInvert(true)
        advanceUntilIdle()
        assertEquals(false, store.volumeKeys.value)
        assertEquals(true, store.volumeInvert.value)
        assertEquals(false, vm.volumeKeys.value)
        assertEquals(true, vm.volumeInvert.value)
    }
}
