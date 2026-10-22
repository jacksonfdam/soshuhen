package app.soshuhen.core

import app.soshuhen.server.SavedServer
import kotlinx.coroutines.flow.Flow

/** The server this phone was set up with, kept across restarts. */
interface ServerStore {
    val saved: Flow<SavedServer?>
    suspend fun save(server: SavedServer)
    suspend fun clear()

    /** The tree URI of the folder the user picked for chapters, once they have. */
    val folder: Flow<String?>
    suspend fun saveFolder(uri: String)

    /** Whether the volume buttons turn the reader's pages. On by default. */
    val volumeKeys: Flow<Boolean>
    suspend fun setVolumeKeys(on: Boolean)

    /** Volume up turns forward instead of back. Off by default. */
    val volumeInvert: Flow<Boolean>
    suspend fun setVolumeInvert(on: Boolean)
}
