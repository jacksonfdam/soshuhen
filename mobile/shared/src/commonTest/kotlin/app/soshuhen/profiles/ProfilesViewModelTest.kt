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
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
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
    private val unlockHeaders = mutableListOf<String?>()
    private var pinOk = false
    private var profilesJson = PROFILES
    // The server refuses a header naming a profile it does not have, on every route.
    private val known = setOf("5", "7")

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
                        val header = request.headers["X-Soshuhen-Profile"]
                        if (header != null && header !in known) {
                            return@addHandler respond(
                                """{"detail":"no profile $header"}""",
                                HttpStatusCode.BadRequest,
                                headersOf(HttpHeaders.ContentType, "application/json"),
                            )
                        }
                        val json = if (request.url.encodedPath.endsWith("/unlock")) {
                            unlocks += request.url.encodedPath
                            unlockHeaders += header
                            """{"ok":$pinOk}"""
                        } else {
                            profilesJson
                        }
                        respond(json, headers = headersOf(HttpHeaders.ContentType, "application/json"))
                    }
                },
            ),
        ),
    )

    private val located = MutableStateFlow(true)

    private fun kotlinx.coroutines.test.TestScope.vm(atHome: Boolean = true): ProfilesViewModel {
        // As in Session: the API and the key follow the saved profile.
        val sessionKey = store.profileKey.map { it ?: 0L }.stateIn(backgroundScope, SharingStarted.Eagerly, 0L)
        val client = store.profileKey.map { api().forProfile(it ?: 0L) }
            .stateIn(backgroundScope, SharingStarted.Eagerly, api())
        return ProfilesViewModel(client, MutableStateFlow(atHome), located, sessionKey, store, local)
    }

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

    @Test fun aDeletedSavedProfileGoesBackToThePicker() = runTest(dispatcher) {
        store.selectProfile(9)
        val vm = vm()
        advanceUntilIdle()
        assertTrue(vm.state.value.atHome)
        assertNull(store.profileKey.value)
        assertEquals(StartRoute.Picker, vm.route.value)
    }

    @Test fun aDeletedProfileWithOneLeftOpensTheManager() = runTest(dispatcher) {
        profilesJson = """[{"id":1,"name":"Me","avatar":"avatar-01","has_pin":false,"is_manager":true,"position":0}]"""
        store.selectProfile(9)
        val vm = vm()
        advanceUntilIdle()
        assertNull(store.profileKey.value)
        assertEquals(StartRoute.Open(0), vm.route.value)
    }

    @Test fun unlockIsAskedWithoutAProfileHeader() = runTest(dispatcher) {
        store.selectProfile(5)
        pinOk = true
        val vm = vm()
        advanceUntilIdle()
        vm.switchProfile()
        vm.choose(vm.named("Ana"))
        vm.submitPin("1234")
        advanceUntilIdle()
        assertEquals(listOf<String?>(null), unlockHeaders)
        assertEquals(7L, store.profileKey.value)
    }

    @Test fun aSecondWrongPinClearsTheErrorWhileItIsChecked() = runTest(dispatcher) {
        pinOk = false
        val vm = vm()
        advanceUntilIdle()
        vm.choose(vm.named("Ana"))
        vm.submitPin("4321")
        advanceUntilIdle()
        assertTrue(vm.state.value.pinError)
        vm.submitPin("9999")
        // Cleared at once, so the pad sees a fresh error and shakes and clears again.
        assertFalse(vm.state.value.pinError)
        advanceUntilIdle()
        assertTrue(vm.state.value.pinError)
    }

    @Test fun nothingOpensUntilTheAppKnowsWhereItIs() = runTest(dispatcher) {
        located.value = false
        store.selectProfile(7)
        val vm = vm(atHome = false)
        // runCurrent, not advanceUntilIdle: that would run the clock past the
        // timeout, which is the other test.
        runCurrent()
        assertEquals(StartRoute.Deciding, vm.route.value)
        located.value = true
        advanceUntilIdle()
        assertEquals(StartRoute.Open(7), vm.route.value)
    }

    @Test fun aSlowLocationCheckIsNotWaitedForForever() = runTest(dispatcher) {
        located.value = false
        store.selectProfile(7)
        val vm = vm(atHome = false)
        advanceTimeBy(DECIDE_TIMEOUT_MS + 1)
        advanceUntilIdle()
        assertEquals(StartRoute.Open(7), vm.route.value)
    }
}
