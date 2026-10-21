package app.soshuhen.core

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
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

    override suspend fun clear() {
        store.edit { it.clear() }
    }

    private companion object {
        val SCHEME = stringPreferencesKey("server_scheme")
        val HOST = stringPreferencesKey("server_host")
        val PORT = intPreferencesKey("server_port")
        val INSTANCE_ID = stringPreferencesKey("instance_id")
    }
}
