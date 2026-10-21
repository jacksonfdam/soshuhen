package app.soshuhen.core

import app.soshuhen.api.SoshuhenApi
import app.soshuhen.server.ServerLocator
import app.soshuhen.server.subnetHosts
import io.ktor.client.HttpClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.merge
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * Which server the screens talk to. Follows the saved server, so choosing one
 * in onboarding or finding it at a new address reaches every screen at once.
 */
class Session(
    private val store: ServerStore,
    private val locator: ServerLocator,
    private val network: NetworkInfo,
    private val client: HttpClient,
    scope: CoroutineScope,
) {
    private val _atHome = MutableStateFlow(false)

    /**
     * True once the saved server's instance id has answered, false once it could
     * not. Away from home it stays false, and the screens read from the device.
     */
    val atHome: StateFlow<Boolean> = _atHome

    val api: StateFlow<SoshuhenApi?> = store.saved
        .map { saved -> saved?.let { SoshuhenApi(it.address.baseUrl, client) } }
        .stateIn(scope, SharingStarted.Eagerly, null)

    init {
        // Keyed on whether a server is saved at all, so choosing one in
        // onboarding starts the first check, and a change of network repeats it
        // instead of the shell repeating it on every composition.
        scope.launch {
            store.saved.map { it != null }.distinctUntilChanged().collectLatest { hasServer ->
                if (hasServer) merge(flowOf(Unit), network.changes).collect { refreshLocation() }
                else _atHome.value = false
            }
        }
    }

    /**
     * Checks the saved address still answers, and if not looks for the same
     * server on the Wi-Fi. An address that cannot be confirmed is kept: away
     * from home the server is simply not there, and it has not moved.
     */
    suspend fun refreshLocation() {
        val saved = store.saved.first()
        if (saved == null) {
            _atHome.value = false
            return
        }
        val hosts = network.wifiAddress()?.let { (ip, prefix) -> subnetHosts(ip, prefix) }
        val found = locator.locate(saved, hosts)
        _atHome.value = found != null
        if (found == null) return
        if (found != saved.address) store.save(saved.copy(address = found))
    }
}
