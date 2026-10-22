package app.soshuhen.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Identity
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.core.Platform
import app.soshuhen.core.ServerStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

data class ServerCard(val baseUrl: String, val identity: Identity?)

class SettingsViewModel(
    private val api: StateFlow<SoshuhenApi?>,
    private val store: ServerStore,
    private val platform: Platform,
) : ViewModel() {
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

    // The answer changes in the system's own screen, so it is read again each
    // time Settings comes back into view.
    fun refreshBattery() {
        _batteryUnrestricted.value = platform.isBatteryUnrestricted()
    }

    fun openBatterySettings() = platform.openBatterySettings()

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

private fun percentDecode(s: String): String {
    val bytes = mutableListOf<Byte>()
    var i = 0
    while (i < s.length) {
        val c = s[i]
        val escaped = if (c == '%' && i + 2 < s.length) s.substring(i + 1, i + 3).toIntOrNull(16) else null
        if (escaped != null) {
            bytes += escaped.toByte()
            i += 3
        } else {
            bytes += c.toString().encodeToByteArray().toList()
            i++
        }
    }
    return bytes.toByteArray().decodeToString()
}
