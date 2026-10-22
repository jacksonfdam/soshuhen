package app.soshuhen.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Identity
import app.soshuhen.core.NetworkInfo
import app.soshuhen.core.ServerStore
import app.soshuhen.server.FoundServer
import app.soshuhen.server.SavedServer
import app.soshuhen.server.ServerAddress
import app.soshuhen.server.ServerScanner
import app.soshuhen.server.parseServerAddress
import app.soshuhen.server.subnetHosts
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/**
 * One state, not a choice between states: a mistyped address must not hide
 * the servers the scan found, and the scan must not wipe the error a moment
 * later.
 */
data class OnboardingUi(
    val found: List<FoundServer> = emptyList(),
    val scanning: Boolean = false,
    val checking: Boolean = false,
    val error: String? = null,
)

private val SLOW_HOST_TIMEOUT = 2.seconds

class OnboardingViewModel(
    private val scanner: ServerScanner,
    private val probe: suspend (ServerAddress) -> Identity?,
    private val network: NetworkInfo,
    private val store: ServerStore,
    private val scanBudget: Duration = 15.seconds,
) : ViewModel() {
    private val _state = MutableStateFlow(OnboardingUi())
    val state: StateFlow<OnboardingUi> = _state
    private var scanning: Job? = null
    // This model outlives the screen (it belongs to the activity), so after a
    // server was chosen and then forgotten it must start over, not resume.
    private var finished = false

    // The network the last scan ran on (null off Wi-Fi), so a change of network
    // can be told from Android repeating the one the phone is already on.
    private var scannedOn: Pair<String, Int>? = null

    init {
        rescan()
        // A fresh install is often opened before the Wi-Fi is up, or on another
        // one; the server should appear without the user thinking to scan again.
        viewModelScope.launch {
            network.changes.collect {
                val now = _state.value
                if (!finished && now.found.isEmpty() && !now.checking && network.wifiAddress() != scannedOn) rescan()
            }
        }
    }

    fun onShown() {
        if (!finished) return
        finished = false
        _state.value = OnboardingUi()
        rescan()
    }

    fun rescan() {
        scanning?.cancel()
        scanning = viewModelScope.launch {
            val wifi = network.wifiAddress()
            scannedOn = wifi
            // Off Wi-Fi there is nothing to scan; the address field is the
            // only way in, and a spinner would only make the person wait.
            if (wifi == null) {
                _state.update { it.copy(scanning = false) }
                return@launch
            }
            _state.update { it.copy(found = emptyList(), scanning = true) }
            // A budget for the whole scan, so a network that drops every probe
            // still ends with the field rather than an endless spinner.
            withTimeoutOrNull(scanBudget) {
                scanner.scan(
                    subnetHosts(wifi.first, wifi.second),
                    retryTimeout = SLOW_HOST_TIMEOUT,
                    warmUp = wifi.first,
                ).collect { server ->
                    _state.update { it.copy(found = it.found + server) }
                }
            }
            _state.update { it.copy(scanning = false) }
        }
    }

    fun choose(server: FoundServer) {
        viewModelScope.launch { save(SavedServer(server.address, server.identity.instanceId)) }
    }

    fun submitAddress(input: String) {
        if (_state.value.checking) return
        val address = parseServerAddress(input)
        if (address == null) {
            _state.update { it.copy(error = "Not an address. Try 192.168.1.20 or 192.168.1.20:8080.") }
            return
        }
        _state.update { it.copy(checking = true, error = null) }
        viewModelScope.launch {
            val identity = probe(address)
            if (identity == null || identity.app != "soshuhen") {
                _state.update {
                    it.copy(checking = false, error = "No Soshuhen server answered at ${address.baseUrl}.")
                }
            } else {
                save(SavedServer(address, identity.instanceId))
            }
        }
    }

    private suspend fun save(server: SavedServer) {
        scanning?.cancel()
        store.save(server)
        finished = true
        _state.update { it.copy(checking = false, scanning = false) }
    }
}
