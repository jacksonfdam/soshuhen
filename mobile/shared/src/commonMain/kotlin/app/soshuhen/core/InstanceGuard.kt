package app.soshuhen.core

import app.soshuhen.server.SavedServer
import kotlinx.coroutines.flow.first

/**
 * The saved server, with the device's own data kept to one installation:
 * every save passes the instance id to [LocalStore.belongTo] first, so the
 * screens never read another server's marks or queue under the new one.
 */
class InstanceGuard(private val servers: ServerStore, private val local: LocalStore) : ServerStore by servers {
    override suspend fun save(server: SavedServer) {
        // A profile id names a person on one server only. The same server at a
        // new address keeps it; another server starts from the picker.
        val before = servers.saved.first()?.instanceId
        local.belongTo(server.instanceId)
        if (before != server.instanceId) servers.selectProfile(null)
        servers.save(server)
    }
}
