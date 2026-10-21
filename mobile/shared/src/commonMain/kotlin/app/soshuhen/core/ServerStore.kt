package app.soshuhen.core

import app.soshuhen.server.SavedServer
import kotlinx.coroutines.flow.Flow

/** The server this phone was set up with, kept across restarts. */
interface ServerStore {
    val saved: Flow<SavedServer?>
    suspend fun save(server: SavedServer)
    suspend fun clear()
}
