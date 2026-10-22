package app.soshuhen.onboarding

import app.soshuhen.core.FakeChapterFolder
import app.soshuhen.core.FakePlatform
import app.soshuhen.core.FakeServerStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class SetupViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @BeforeTest fun setUp() = Dispatchers.setMain(dispatcher)
    @AfterTest fun tearDown() = Dispatchers.resetMain()

    @Test fun theFolderStepComesFirstAndIsRequired() = runTest(dispatcher) {
        val store = FakeServerStore()
        val platform = FakePlatform(picked = null)
        val vm = SetupViewModel(store, platform, FakeChapterFolder())
        advanceUntilIdle()
        assertTrue(vm.ready.value)
        assertEquals(SetupStep.Folder, vm.step.value)
        vm.pickFolder()
        advanceUntilIdle()
        assertEquals(SetupStep.Folder, vm.step.value)
        assertNull(store.folder.value)

        platform.picked = "content://tree/Manga"
        vm.pickFolder()
        advanceUntilIdle()
        assertEquals("content://tree/Manga", store.folder.value)
        assertEquals(SetupStep.Notifications, vm.step.value)
    }

    @Test fun notificationsAreSkippedBelowAndroid13() = runTest(dispatcher) {
        val vm = SetupViewModel(FakeServerStore(), FakePlatform(needsNotificationPermission = false), FakeChapterFolder())
        advanceUntilIdle()
        vm.pickFolder()
        advanceUntilIdle()
        assertEquals(SetupStep.Battery, vm.step.value)
    }

    @Test fun batteryIsSkippedWhenAlreadyUnrestricted() = runTest(dispatcher) {
        val platform = FakePlatform(unrestricted = true)
        val vm = SetupViewModel(FakeServerStore(), platform, FakeChapterFolder())
        advanceUntilIdle()
        vm.pickFolder()
        advanceUntilIdle()
        vm.allowNotifications()
        advanceUntilIdle()
        assertEquals(1, platform.notificationRequests)
        assertNull(vm.step.value)
    }

    @Test fun notNowIsNotAskedAgain() = runTest(dispatcher) {
        val store = FakeServerStore()
        val platform = FakePlatform()
        val first = SetupViewModel(store, platform, FakeChapterFolder())
        advanceUntilIdle()
        first.pickFolder()
        advanceUntilIdle()
        first.notNow()
        advanceUntilIdle()
        assertEquals(SetupStep.Battery, first.step.value)
        first.skipBattery()
        advanceUntilIdle()
        assertNull(first.step.value)
        assertEquals(0, platform.notificationRequests)

        val again = SetupViewModel(store, platform, FakeChapterFolder())
        advanceUntilIdle()
        assertNull(again.step.value)
    }

    @Test fun openingBatterySettingsCountsAsOffered() = runTest(dispatcher) {
        val store = FakeServerStore()
        val platform = FakePlatform(needsNotificationPermission = false)
        val vm = SetupViewModel(store, platform, FakeChapterFolder())
        advanceUntilIdle()
        vm.pickFolder()
        advanceUntilIdle()
        vm.openBatterySettings()
        advanceUntilIdle()
        assertEquals(1, platform.batterySettingsOpened)
        assertNull(vm.step.value)
        assertNull(SetupViewModel(store, platform, FakeChapterFolder()).also { advanceUntilIdle() }.step.value)
    }

    @Test fun aFolderThatLostItsPermissionAsksAgain() = runTest(dispatcher) {
        val store = FakeServerStore()
        store.saveFolder("content://tree/Manga")
        val platform = FakePlatform(unrestricted = true)
        store.markSetupOffered(SetupStep.Notifications.name)
        val lost = FakeChapterFolder().apply { available = false }
        val vm = SetupViewModel(store, platform, lost)
        advanceUntilIdle()
        assertEquals(SetupStep.Folder, vm.step.value)

        val fine = SetupViewModel(store, platform, FakeChapterFolder())
        advanceUntilIdle()
        assertNull(fine.step.value)
    }
}
