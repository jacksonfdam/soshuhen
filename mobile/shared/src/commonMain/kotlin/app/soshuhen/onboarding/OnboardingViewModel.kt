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
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

sealed interface OnboardingState {
    data class Scanning(val found: List<FoundServer>) : OnboardingState
    data class Done(val found: List<FoundServer>) : OnboardingState
    data object Checking : OnboardingState
    data class Failed(val message: String) : OnboardingState
}

class OnboardingViewModel(
    private val scanner: ServerScanner,
    private val probe: suspend (ServerAddress) -> Identity?,
    private val network: NetworkInfo,
    private val store: ServerStore,
    private val scanBudget: Duration = 15.seconds,
) : ViewModel() {
    private val _state = MutableStateFlow<OnboardingState>(OnboardingState.Scanning(emptyList()))
    val state: StateFlow<OnboardingState> = _state
    private var scanning: Job? = null

    init {
        rescan()
    }

    fun rescan() {
        scanning?.cancel()
        scanning = viewModelScope.launch {
            val wifi = network.wifiAddress()
            if (wifi == null) {
                // Off Wi-Fi there is nothing to scan; the address field is the
                // only way in, and a spinner would only make the person wait.
                _state.value = OnboardingState.Done(emptyList())
                return@launch
            }
            val found = mutableListOf<FoundServer>()
            _state.value = OnboardingState.Scanning(emptyList())
            // A budget for the whole scan, so a network that drops every probe
            // still ends with the field rather than an endless spinner.
            withTimeoutOrNull(scanBudget) {
                scanner.scan(subnetHosts(wifi.first, wifi.second)).collect {
                    found += it
                    _state.value = OnboardingState.Scanning(found.toList())
                }
            }
            _state.value = OnboardingState.Done(found.toList())
        }
    }

    fun choose(server: FoundServer) {
        viewModelScope.launch { store.save(SavedServer(server.address, server.identity.instanceId)) }
    }

    fun submitAddress(input: String) {
        val address = parseServerAddress(input)
        if (address == null) {
            _state.value = OnboardingState.Failed("Not an address. Try 192.168.1.20 or 192.168.1.20:8080.")
            return
        }
        scanning?.cancel()
        _state.value = OnboardingState.Checking
        viewModelScope.launch {
            val identity = probe(address)
            if (identity == null || identity.app != "soshuhen") {
                _state.value = OnboardingState.Failed("No Soshuhen server answered at ${address.baseUrl}.")
            } else {
                store.save(SavedServer(address, identity.instanceId))
            }
        }
    }
}
