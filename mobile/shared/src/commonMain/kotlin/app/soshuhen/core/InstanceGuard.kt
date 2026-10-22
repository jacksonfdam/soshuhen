package app.soshuhen.core

import app.soshuhen.server.SavedServer

/**
 * The saved server, with the device's own data kept to one installation:
 * every save passes the instance id to [LocalStore.belongTo] first, so the
 * screens never read another server's marks or queue under the new one.
 */
class InstanceGuard(private val servers: ServerStore, private val local: LocalStore) : ServerStore by servers {
    override suspend fun save(server: SavedServer) {
        local.belongTo(server.instanceId)
        servers.save(server)
    }
}
