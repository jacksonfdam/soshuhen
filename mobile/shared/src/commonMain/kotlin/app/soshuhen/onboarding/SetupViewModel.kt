package app.soshuhen.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.core.ChapterFolder
import app.soshuhen.core.Platform
import app.soshuhen.core.ServerStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

enum class SetupStep { Folder, Notifications, Battery }

/**
 * The steps between choosing a server and the library. Only the folder is
 * required: without it there is nowhere to copy to. The other two are asked
 * once each, so "Not now" means not now rather than every launch.
 */
class SetupViewModel(
    private val store: ServerStore,
    private val platform: Platform,
    private val folder: ChapterFolder,
) : ViewModel() {
    private val _ready = MutableStateFlow(false)

    /** False until the first step is known, so a set-up phone never sees a step flash before the library. */
    val ready: StateFlow<Boolean> = _ready

    private val _step = MutableStateFlow<SetupStep?>(null)

    /** The step to show; null once there is nothing left to ask. */
    val step: StateFlow<SetupStep?> = _step

    // Set when the user picks a folder here. The folder object may learn of the
    // new URI a moment after the store does, and asking it then would send the
    // user straight back to the picker.
    private var pickedNow = false

    init {
        viewModelScope.launch {
            _step.value = next()
            _ready.value = true
        }
    }

    private suspend fun next(): SetupStep? {
        val hasFolder = pickedNow || (store.folder.first() != null && folder.isAvailable())
        if (!hasFolder) return SetupStep.Folder
        val offered = store.setupOffered.first()
        if (platform.needsNotificationPermission && SetupStep.Notifications.name !in offered) return SetupStep.Notifications
        if (!platform.isBatteryUnrestricted() && SetupStep.Battery.name !in offered) return SetupStep.Battery
        return null
    }

    fun pickFolder() {
        viewModelScope.launch {
            val uri = platform.pickFolder() ?: return@launch
            store.saveFolder(uri)
            pickedNow = true
            _step.value = next()
        }
    }

    fun allowNotifications() {
        viewModelScope.launch {
            platform.requestNotifications()
            offered(SetupStep.Notifications)
        }
    }

    fun notNow() {
        viewModelScope.launch { offered(SetupStep.Notifications) }
    }

    fun openBatterySettings() {
        platform.openBatterySettings()
        viewModelScope.launch { offered(SetupStep.Battery) }
    }

    fun skipBattery() {
        viewModelScope.launch { offered(SetupStep.Battery) }
    }

    private suspend fun offered(step: SetupStep) {
        store.markSetupOffered(step.name)
        _step.value = next()
    }
}
