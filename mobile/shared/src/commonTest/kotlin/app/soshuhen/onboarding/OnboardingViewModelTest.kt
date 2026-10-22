package app.soshuhen.onboarding

import app.soshuhen.api.Identity
import app.soshuhen.core.FakeNetworkInfo
import app.soshuhen.core.FakeServerStore
import app.soshuhen.server.SavedServer
import app.soshuhen.server.ServerAddress
import app.soshuhen.server.ServerScanner
import app.soshuhen.server.identity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.seconds

@OptIn(ExperimentalCoroutinesApi::class)
class OnboardingViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val store = FakeServerStore()

    @BeforeTest fun setUp() = Dispatchers.setMain(dispatcher)
    @AfterTest fun tearDown() = Dispatchers.resetMain()

    private fun vm(
        wifi: Pair<String, Int>? = "10.0.0.1" to 24,
        answers: Map<String, suspend () -> Identity?> = emptyMap(),
        network: FakeNetworkInfo = FakeNetworkInfo(wifi),
    ): OnboardingViewModel {
        val probe: suspend (ServerAddress) -> Identity? = { answers[it.host]?.invoke() }
        return OnboardingViewModel(ServerScanner(probe), probe, network, store, scanBudget = 15.seconds)
    }

    private fun TestScope.settled(vm: OnboardingViewModel): OnboardingUi {
        advanceUntilIdle()
        return vm.state.value
    }

    @Test fun offWifiSkipsTheScanAndOffersTheField() = runTest(dispatcher) {
        assertEquals(OnboardingUi(), settled(vm(wifi = null)))
    }

    @Test fun aScanThatFindsNothingEndsWithinTheBudget() = runTest(dispatcher) {
        val hang: suspend () -> Identity? = { awaitCancellation() }
        val ui = settled(vm(answers = (2..254).associate { "10.0.0.$it" to hang }))
        assertFalse(ui.scanning)
        assertTrue(ui.found.isEmpty())
        assertTrue(testScheduler.currentTime <= 15_000)
    }

    @Test fun foundServersAreListed() = runTest(dispatcher) {
        val ui = settled(vm(answers = mapOf("10.0.0.2" to { identity(id = "a") }, "10.0.0.3" to { identity(id = "b") })))
        assertEquals(setOf("10.0.0.2", "10.0.0.3"), ui.found.map { it.address.host }.toSet())
    }

    @Test fun choosingSavesAddressAndInstanceId() = runTest(dispatcher) {
        val model = vm(answers = mapOf("10.0.0.2" to { identity(id = "id-1") }))
        model.choose(settled(model).found.single())
        advanceUntilIdle()
        assertEquals(SavedServer(ServerAddress("http", "10.0.0.2", 8080), "id-1"), store.saved.value)
    }

    @Test fun aTypedAddressThatAnswersIsSavedAndStopsChecking() = runTest(dispatcher) {
        val model = vm(wifi = null, answers = mapOf("10.0.0.9" to { identity(id = "id-9") }))
        settled(model)
        model.submitAddress("10.0.0.9")
        val ui = settled(model)
        assertEquals("id-9", store.saved.value?.instanceId)
        assertFalse(ui.checking)
    }

    @Test fun aTypedAddressThatIsNotSoshuhenFails() = runTest(dispatcher) {
        val model = vm(wifi = null)
        settled(model)
        model.submitAddress("10.0.0.9")
        assertEquals("No Soshuhen server answered at http://10.0.0.9:8080.", settled(model).error)
    }

    @Test fun garbageInputFailsWithTheExample() = runTest(dispatcher) {
        val model = vm(wifi = null)
        settled(model)
        model.submitAddress("abc def")
        assertEquals("Not an address. Try 192.168.1.20 or 192.168.1.20:8080.", settled(model).error)
    }

    @Test fun anErrorSurvivesTheScanAndKeepsTheList() = runTest(dispatcher) {
        val slow: suspend () -> Identity? = { delay(300); identity(id = "late") }
        val model = vm(answers = mapOf("10.0.0.2" to { identity(id = "early") }, "10.0.0.3" to slow))
        advanceTimeBy(100)
        model.submitAddress("abc def")
        val ui = settled(model)
        assertEquals("Not an address. Try 192.168.1.20 or 192.168.1.20:8080.", ui.error)
        assertEquals(setOf("early", "late"), ui.found.map { it.identity.instanceId }.toSet())
    }

    @Test fun shownAgainAfterChangeServerStartsFresh() = runTest(dispatcher) {
        val model = vm(answers = mapOf("10.0.0.2" to { identity(id = "id-1") }))
        model.submitAddress("10.0.0.9")
        settled(model)
        model.choose(model.state.value.found.single())
        advanceUntilIdle()
        model.onShown()
        val ui = settled(model)
        assertNull(ui.error)
        assertFalse(ui.checking)
        assertEquals(1, ui.found.size)
    }

    @Test fun onShownBeforeFinishingDoesNotRestartTheScan() = runTest(dispatcher) {
        var probes = 0
        val model = vm(answers = mapOf("10.0.0.2" to { probes++; identity() }))
        settled(model)
        model.onShown()
        settled(model)
        assertEquals(1, probes)
    }

    @Test fun aNetworkThatComesUpWhileShownIsScanned() = runTest(dispatcher) {
        val network = FakeNetworkInfo(null)
        val model = vm(answers = mapOf("10.0.0.2" to { identity(id = "id-1") }), network = network)
        assertTrue(settled(model).found.isEmpty())
        network.wifi = "10.0.0.1" to 24
        network.changeEvents.emit(Unit)
        assertEquals(listOf("10.0.0.2"), settled(model).found.map { it.address.host })
    }

    @Test fun aChangeOnTheSameNetworkDoesNotRestartTheScan() = runTest(dispatcher) {
        val network = FakeNetworkInfo("10.0.0.1" to 24)
        var probes = 0
        val model = vm(answers = mapOf("10.0.0.2" to { probes++; delay(300); null }), network = network)
        advanceTimeBy(100)
        network.changeEvents.emit(Unit)
        settled(model)
        assertEquals(1, probes)
    }
}
