package app.soshuhen.server

import app.soshuhen.api.Identity
import kotlinx.coroutines.flow.firstOrNull

/** Finds the server this phone was set up with, wherever DHCP has put it. */
class ServerLocator(
    private val probe: suspend (ServerAddress) -> Identity?,
    private val scanner: ServerScanner,
) {
    /**
     * [hosts] is null off Wi-Fi: a scan over mobile data would probe the
     * carrier's network, and the server is never there.
     */
    suspend fun locate(saved: SavedServer, hosts: List<String>?): ServerAddress? {
        if (probe(saved.address)?.instanceId == saved.instanceId) return saved.address
        if (hosts == null) return null
        // By instance id, not by name: a second installation on the same
        // network must not be taken for this one.
        return scanner.scan(hosts, port = saved.address.port)
            .firstOrNull { it.identity.instanceId == saved.instanceId }
            ?.address
    }
}
