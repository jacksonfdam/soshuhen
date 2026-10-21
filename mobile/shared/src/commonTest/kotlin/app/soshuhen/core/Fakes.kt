package app.soshuhen.core

import app.soshuhen.server.SavedServer
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.onStart
import kotlinx.coroutines.flow.StateFlow

class FakeServerStore(initial: SavedServer? = null) : ServerStore {
    private val state = MutableStateFlow(initial)
    override val saved: StateFlow<SavedServer?> = state
    override suspend fun save(server: SavedServer) { state.value = server }
    override suspend fun clear() { state.value = null }
    private val picked = MutableStateFlow<String?>(null)
    override val folder: StateFlow<String?> = picked
    override suspend fun saveFolder(uri: String) { picked.value = uri }
}

class FakeNetworkInfo(var wifi: Pair<String, Int>?) : NetworkInfo {
    val changeEvents = MutableSharedFlow<Unit>()
    // Like the Android one: says so once on collection, then on each change.
    override val changes: Flow<Unit> = changeEvents.onStart { emit(Unit) }
    override fun wifiAddress(): Pair<String, Int>? = wifi
}
