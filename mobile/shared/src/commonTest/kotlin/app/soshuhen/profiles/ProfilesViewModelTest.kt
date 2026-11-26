package app.soshuhen.profiles

import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.FakeServerStore
import app.soshuhen.core.LocalStore
import app.soshuhen.core.testDatabase
import app.soshuhen.db.SoshuhenDatabase
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
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
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val PROFILES = """
[{"id":1,"name":"Me","avatar":"avatar-01","has_pin":false,"is_manager":true,"position":0},
 {"id":5,"name":"Bia","avatar":"avatar-03","has_pin":false,"is_manager":false,"position":1},
 {"id":7,"name":"Ana","avatar":"avatar-12","has_pin":true,"is_manager":false,"position":2}]
"""

@OptIn(ExperimentalCoroutinesApi::class)
class ProfilesViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private lateinit var db: SoshuhenDatabase
    private lateinit var local: LocalStore
    private val store = FakeServerStore()
    private val unlocks = mutableListOf<String>()
    private var pinOk = false

    @BeforeTest fun setUp() {
        Dispatchers.setMain(dispatcher)
        db = testDatabase(dispatcher)
        local = LocalStore(db)
    }

    @AfterTest fun tearDown() {
        db.close()
        Dispatchers.resetMain()
    }

    private fun api() = SoshuhenApi(
        "http://s",
        soshuhenHttpClient(
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@ProfilesViewModelTest.dispatcher
                    addHandler { request ->
                        val json = if (request.url.encodedPath.endsWith("/unlock")) {
                            unlocks += request.url.encodedPath
                            """{"ok":$pinOk}"""
                        } else {
                            PROFILES
                        }
                        respond(json, headers = headersOf(HttpHeaders.ContentType, "application/json"))
                    }
                },
            ),
        ),
    )

    private fun vm(atHome: Boolean = true) =
        ProfilesViewModel(MutableStateFlow(api()), MutableStateFlow(atHome), store, local)

    private fun ProfilesViewModel.named(name: String) = state.value.profiles.first { it.name == name }

    @Test fun aProfileWithoutPinOpensAtOnce() = runTest(dispatcher) {
        val vm = vm()
        advanceUntilIdle()
        vm.choose(vm.named("Bia"))
        advanceUntilIdle()
        assertEquals(5L, store.profileKey.value)
        assertEquals(StartRoute.Open(5), vm.route.value)
    }

    @Test fun choosingTheManagerStoresZero() = runTest(dispatcher) {
        val vm = vm()
        advanceUntilIdle()
        vm.choose(vm.named("Me"))
        advanceUntilIdle()
        assertEquals(0L, store.profileKey.value)
    }

    @Test fun aWrongPinStaysOnThePad() = runTest(dispatcher) {
        pinOk = false
        val vm = vm()
        advanceUntilIdle()
        vm.choose(vm.named("Ana"))
        assertEquals("Ana", vm.state.value.pinFor?.name)
        vm.submitPin("4321")
        advanceUntilIdle()
        assertTrue(vm.state.value.pinError)
        assertEquals("Ana", vm.state.value.pinFor?.name)
        assertNull(store.profileKey.value)
        assertEquals(listOf("/api/profiles/7/unlock"), unlocks)
    }

    @Test fun theRightPinOpens() = runTest(dispatcher) {
        pinOk = true
        val vm = vm()
        advanceUntilIdle()
        vm.choose(vm.named("Ana"))
        vm.submitPin("1234")
        advanceUntilIdle()
        assertEquals(7L, store.profileKey.value)
        assertNull(vm.state.value.pinFor)
    }

    @Test fun offlineAPinProfileCannotBeOpened() = runTest(dispatcher) {
        local.putProfiles(PROFILES)
        val vm = vm(atHome = false)
        advanceUntilIdle()
        vm.choose(vm.named("Ana"))
        advanceUntilIdle()
        assertNull(vm.state.value.pinFor)
        assertNull(store.profileKey.value)
        assertEquals(emptyList(), unlocks)
    }

    @Test fun profilesComeFromTheSnapshotAwayFromHome() = runTest(dispatcher) {
        local.putProfiles(PROFILES)
        val vm = vm(atHome = false)
        advanceUntilIdle()
        assertEquals(listOf("Me", "Bia", "Ana"), vm.state.value.profiles.map { it.name })
        assertFalse(vm.state.value.atHome)
    }
}
