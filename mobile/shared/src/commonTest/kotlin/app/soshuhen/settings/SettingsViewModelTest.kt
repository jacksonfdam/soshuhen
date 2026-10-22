package app.soshuhen.settings

import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.FakePlatform
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
        val vm = SettingsViewModel(api, FakeServerStore(), FakePlatform())
        advanceUntilIdle()
        api.value = api("http://10.0.0.31:8080")
        advanceUntilIdle()
        assertEquals("http://10.0.0.31:8080", vm.server.value?.baseUrl)
    }

    @Test fun volumeKeysTurnPagesUntilSwitchedOff() = runTest(dispatcher) {
        val store = FakeServerStore()
        val vm = SettingsViewModel(MutableStateFlow(null), store, FakePlatform())
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

    @Test fun changeFolderSavesThePickedOneAndBackingOutKeepsTheOld() = runTest(dispatcher) {
        val store = FakeServerStore()
        store.saveFolder("content://com.android.externalstorage.documents/tree/primary%3ADocuments%2FManga")
        val platform = FakePlatform(picked = null)
        val vm = SettingsViewModel(MutableStateFlow(null), store, platform)
        advanceUntilIdle()
        assertEquals("Documents/Manga", vm.folder.value)
        vm.changeFolder()
        advanceUntilIdle()
        assertEquals("Documents/Manga", vm.folder.value)
        platform.picked = "content://com.android.externalstorage.documents/tree/1A2B-3C4D%3AComics"
        vm.changeFolder()
        advanceUntilIdle()
        assertEquals("content://com.android.externalstorage.documents/tree/1A2B-3C4D%3AComics", store.folder.value)
        assertEquals("1A2B-3C4D: Comics", vm.folder.value)
    }

    @Test fun batteryStatusIsReadAgainWhenAsked() = runTest(dispatcher) {
        val platform = FakePlatform(unrestricted = false)
        val vm = SettingsViewModel(MutableStateFlow(null), FakeServerStore(), platform)
        advanceUntilIdle()
        assertEquals(false, vm.batteryUnrestricted.value)
        vm.openBatterySettings()
        platform.unrestricted = true
        vm.refreshSystemState()
        assertEquals(1, platform.batterySettingsOpened)
        assertEquals(true, vm.batteryUnrestricted.value)
    }

    @Test fun notificationsShowWhatAndroidSaysAndOpenItsSettings() = runTest(dispatcher) {
        val platform = FakePlatform(notificationsOn = false)
        val vm = SettingsViewModel(MutableStateFlow(null), FakeServerStore(), platform)
        assertEquals(false, vm.notificationsOn.value)
        vm.openNotificationSettings()
        assertEquals(1, platform.notificationSettingsOpened)
        // Turned on in Android's own screen; read again when Settings is back.
        platform.notificationsOn = true
        vm.refreshSystemState()
        assertEquals(true, vm.notificationsOn.value)
    }
}
