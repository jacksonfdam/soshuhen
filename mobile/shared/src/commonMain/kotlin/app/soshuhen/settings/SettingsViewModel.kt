package app.soshuhen.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Identity
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.core.ChapterFolder
import app.soshuhen.core.FolderUse
import app.soshuhen.core.LocalStore
import app.soshuhen.core.folderStorage
import app.soshuhen.core.Platform
import app.soshuhen.core.Sync
import app.soshuhen.core.SyncFlow
import app.soshuhen.core.VolumeSpace
import app.soshuhen.core.percentDecode
import app.soshuhen.core.ServerStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

data class ServerCard(val baseUrl: String, val identity: Identity?)

/**
 * What the app's folder takes, measured from the folder, plus what Android says
 * is free on that volume. [notMarked] is the part no marked series owns.
 */
data class StorageUi(val used: Long, val space: VolumeSpace?, val perSeries: List<FolderUse>, val notMarked: Long)

class SettingsViewModel(
    private val api: StateFlow<SoshuhenApi?>,
    private val store: ServerStore,
    private val platform: Platform,
    local: LocalStore? = null,
    sync: Sync? = null,
    folder: ChapterFolder? = null,
) : ViewModel() {
    // The index only says when to measure again: every file an import lands
    // changes it. Conflated, so a burst of copies costs one walk, not one each.
    val storage: StateFlow<StorageUi?> = if (local != null && folder != null) {
        combine(local.storageBySeries(), store.folder, local.markedIds()) { _, uri, marked -> uri to marked }
            .conflate()
            .map { (uri, marked) ->
                try {
                    val s = folderStorage(folder.usage(), local.seriesSnapshot().orEmpty(), marked)
                    StorageUi(s.used, uri?.let(platform::freeSpace), s.perSeries, s.notMarked)
                } catch (e: CancellationException) {
                    throw e
                } catch (_: Exception) {
                    // A revoked or missing folder: Settings already says so beside the folder.
                    null
                }
            }
            .stateIn(viewModelScope, SharingStarted.Eagerly, null)
    } else {
        MutableStateFlow(null)
    }

    /** Every marked series: copy what is missing, then ask about the server's copies. */
    val sync: SyncFlow? = sync?.let { s ->
        SyncFlow(
            run = { progress -> s.run(null, progress) },
            offload = s::offload,
            scope = viewModelScope,
            canOffload = s.canOffload,
        )
    }

    private val _server = MutableStateFlow<ServerCard?>(null)
    val server: StateFlow<ServerCard?> = _server

    val volumeKeys: StateFlow<Boolean> = store.volumeKeys.stateIn(viewModelScope, SharingStarted.Eagerly, true)
    val volumeInvert: StateFlow<Boolean> = store.volumeInvert.stateIn(viewModelScope, SharingStarted.Eagerly, false)

    /** The picked folder as a person would name it, or null before one is picked. */
    val folder: StateFlow<String?> = store.folder.map { it?.let(::folderLabel) }
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    /**
     * Saves the newly picked folder; new copies go there. Chapters already
     * copied stay indexed by their own URI and stay readable where they are:
     * the old folder's permission is kept and nothing is moved or deleted.
     */
    fun changeFolder() {
        viewModelScope.launch {
            val uri = platform.pickFolder() ?: return@launch
            store.saveFolder(uri)
        }
    }

    private val _batteryUnrestricted = MutableStateFlow(platform.isBatteryUnrestricted())
    val batteryUnrestricted: StateFlow<Boolean> = _batteryUnrestricted

    private val _notificationsOn = MutableStateFlow(platform.areNotificationsEnabled())
    val notificationsOn: StateFlow<Boolean> = _notificationsOn

    // Both answers change in the system's own screens, so they are read again
    // each time Settings comes back into view.
    fun refreshSystemState() {
        _batteryUnrestricted.value = platform.isBatteryUnrestricted()
        _notificationsOn.value = platform.areNotificationsEnabled()
    }

    fun openBatterySettings() = platform.openBatterySettings()

    // "Not now" at setup is never asked again; this is where it is undone.
    fun openNotificationSettings() = platform.openNotificationSettings()

    fun setVolumeKeys(on: Boolean) {
        viewModelScope.launch { store.setVolumeKeys(on) }
    }

    fun setVolumeInvert(on: Boolean) {
        viewModelScope.launch { store.setVolumeInvert(on) }
    }

    init {
        viewModelScope.launch {
            api.filterNotNull().distinctUntilChanged().collectLatest { client -> show(client) }
        }
    }

    private suspend fun show(client: SoshuhenApi) {
        _server.value = ServerCard(client.baseUrl, null)
        val identity = try {
            client.identity()
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            null
        }
        _server.value = ServerCard(client.baseUrl, identity)
    }

    /** Back to onboarding: the app follows the saved server, and there is none. */
    fun forget() {
        viewModelScope.launch { store.clear() }
    }
}

/**
 * A Storage Access Framework tree URI ends in an encoded `volume:path`. The
 * phone's own storage is "primary", which says nothing to a reader, so only
 * the path is shown for it; a card keeps its volume name.
 */
internal fun folderLabel(uri: String): String {
    val encoded = uri.substringAfterLast("/tree/", missingDelimiterValue = "")
    if (encoded.isEmpty()) return uri
    val decoded = percentDecode(encoded.substringBefore('/'))
    val volume = decoded.substringBefore(':', missingDelimiterValue = "")
    val path = decoded.substringAfter(':')
    return when {
        volume.isEmpty() -> decoded
        volume == "primary" -> path.ifEmpty { "Internal storage" }
        else -> if (path.isEmpty()) volume else "$volume: $path"
    }
}
