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
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
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
    ): OnboardingViewModel {
        val probe: suspend (ServerAddress) -> Identity? = { answers[it.host]?.invoke() }
        return OnboardingViewModel(ServerScanner(probe), probe, FakeNetworkInfo(wifi), store, scanBudget = 15.seconds)
    }

    private fun TestScope.settled(vm: OnboardingViewModel): OnboardingState {
        advanceUntilIdle()
        return vm.state.value
    }

    @Test fun offWifiSkipsTheScanAndOffersTheField() = runTest(dispatcher) {
        assertEquals(OnboardingState.Done(emptyList()), settled(vm(wifi = null)))
    }

    @Test fun aScanThatFindsNothingEndsWithinTheBudget() = runTest(dispatcher) {
        val hang: suspend () -> Identity? = { awaitCancellation() }
        val model = vm(answers = (2..254).associate { "10.0.0.$it" to hang })
        assertEquals(OnboardingState.Done(emptyList()), settled(model))
        assertEquals(true, testScheduler.currentTime <= 15_000)
    }

    @Test fun foundServersAreListed() = runTest(dispatcher) {
        val model = vm(answers = mapOf("10.0.0.2" to { identity(id = "a") }, "10.0.0.3" to { identity(id = "b") }))
        val state = assertIs<OnboardingState.Done>(settled(model))
        assertEquals(setOf("10.0.0.2", "10.0.0.3"), state.found.map { it.address.host }.toSet())
    }

    @Test fun choosingSavesAddressAndInstanceId() = runTest(dispatcher) {
        val model = vm(answers = mapOf("10.0.0.2" to { identity(id = "id-1") }))
        val found = assertIs<OnboardingState.Done>(settled(model)).found.single()
        model.choose(found)
        advanceUntilIdle()
        assertEquals(SavedServer(ServerAddress("http", "10.0.0.2", 8080), "id-1"), store.saved.value)
    }

    @Test fun aTypedAddressThatAnswersIsSaved() = runTest(dispatcher) {
        val model = vm(wifi = null, answers = mapOf("10.0.0.9" to { identity(id = "id-9") }))
        settled(model)
        model.submitAddress("10.0.0.9")
        advanceUntilIdle()
        assertEquals("id-9", store.saved.value?.instanceId)
    }

    @Test fun aTypedAddressThatIsNotSoshuhenFails() = runTest(dispatcher) {
        val model = vm(wifi = null)
        settled(model)
        model.submitAddress("10.0.0.9")
        assertEquals(OnboardingState.Failed("No Soshuhen server answered at http://10.0.0.9:8080."), settled(model))
    }

    @Test fun garbageInputFailsWithTheExample() = runTest(dispatcher) {
        val model = vm(wifi = null)
        settled(model)
        model.submitAddress("abc def")
        assertEquals(OnboardingState.Failed("Not an address. Try 192.168.1.20 or 192.168.1.20:8080."), settled(model))
    }
}
