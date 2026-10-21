package app.soshuhen.core

import app.soshuhen.api.SoshuhenApi
import app.soshuhen.server.ServerLocator
import app.soshuhen.server.subnetHosts
import io.ktor.client.HttpClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

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
    val api: StateFlow<SoshuhenApi?> = store.saved
        .map { saved -> saved?.let { SoshuhenApi(it.address.baseUrl, client) } }
        .stateIn(scope, SharingStarted.Eagerly, null)

    /**
     * Checks the saved address still answers, and if not looks for the same
     * server on the Wi-Fi. An address that cannot be confirmed is kept: away
     * from home the server is simply not there, and it has not moved.
     */
    suspend fun refreshLocation() {
        val saved = store.saved.first() ?: return
        val hosts = network.wifiAddress()?.let { (ip, prefix) -> subnetHosts(ip, prefix) }
        val found = locator.locate(saved, hosts) ?: return
        if (found != saved.address) store.save(saved.copy(address = found))
    }
}
