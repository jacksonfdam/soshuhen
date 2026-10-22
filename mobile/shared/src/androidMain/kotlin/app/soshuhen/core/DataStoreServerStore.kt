package app.soshuhen.core

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import app.soshuhen.server.SavedServer
import app.soshuhen.server.ServerAddress
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import okio.Path.Companion.toPath

class DataStoreServerStore(context: Context) : ServerStore {
    private val store: DataStore<Preferences> = PreferenceDataStoreFactory.createWithPath(
        produceFile = { context.filesDir.resolve("server.preferences_pb").absolutePath.toPath() },
    )

    override val saved: Flow<SavedServer?> = store.data.map { prefs ->
        val host = prefs[HOST] ?: return@map null
        val id = prefs[INSTANCE_ID] ?: return@map null
        SavedServer(ServerAddress(prefs[SCHEME] ?: "http", host, prefs[PORT] ?: 8080), id)
    }

    override suspend fun save(server: SavedServer) {
        store.edit {
            it[SCHEME] = server.address.scheme
            it[HOST] = server.address.host
            it[PORT] = server.address.port
            it[INSTANCE_ID] = server.instanceId
        }
    }

    // Kept across a change of server: the folder and the volume buttons belong
    // to the phone, and the files in the folder are the user's, not the server's.
    override suspend fun clear() {
        store.edit { prefs -> prefs.asMap().keys.filter { it !in DEVICE }.forEach { prefs.remove(it) } }
    }

    override val folder: Flow<String?> = store.data.map { it[FOLDER] }

    override suspend fun saveFolder(uri: String) {
        store.edit { it[FOLDER] = uri }
    }

    override val volumeKeys: Flow<Boolean> = store.data.map { it[VOLUME_KEYS] ?: true }

    override suspend fun setVolumeKeys(on: Boolean) {
        store.edit { it[VOLUME_KEYS] = on }
    }

    override val volumeInvert: Flow<Boolean> = store.data.map { it[VOLUME_INVERT] ?: false }

    override suspend fun setVolumeInvert(on: Boolean) {
        store.edit { it[VOLUME_INVERT] = on }
    }

    override val setupOffered: Flow<Set<String>> = store.data.map { it[SETUP_OFFERED] ?: emptySet() }

    override suspend fun markSetupOffered(step: String) {
        store.edit { it[SETUP_OFFERED] = (it[SETUP_OFFERED] ?: emptySet()) + step }
    }

    private companion object {
        val SCHEME = stringPreferencesKey("server_scheme")
        val HOST = stringPreferencesKey("server_host")
        val PORT = intPreferencesKey("server_port")
        val FOLDER = stringPreferencesKey("chapter_folder")
        val INSTANCE_ID = stringPreferencesKey("instance_id")
        val VOLUME_KEYS = booleanPreferencesKey("volume_keys")
        val VOLUME_INVERT = booleanPreferencesKey("volume_invert")
        val SETUP_OFFERED = stringSetPreferencesKey("setup_offered")

        // Permissions and battery settings are the phone's too: a new server
        // does not make "Not now" worth asking again.
        val DEVICE: Set<Preferences.Key<*>> = setOf(FOLDER, VOLUME_KEYS, VOLUME_INVERT, SETUP_OFFERED)
    }
}
