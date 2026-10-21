package app.soshuhen.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Identity
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.core.ServerStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

data class ServerCard(val baseUrl: String, val identity: Identity?)

class SettingsViewModel(
    private val api: StateFlow<SoshuhenApi?>,
    private val store: ServerStore,
) : ViewModel() {
    private val _server = MutableStateFlow<ServerCard?>(null)
    val server: StateFlow<ServerCard?> = _server

    init {
        viewModelScope.launch {
            val client = api.filterNotNull().first()
            _server.value = ServerCard(client.baseUrl, null)
            val identity = try {
                client.identity()
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                null
            }
            _server.value = ServerCard(client.baseUrl, identity)
        }
    }

    /** Back to onboarding: the app follows the saved server, and there is none. */
    fun forget() {
        viewModelScope.launch { store.clear() }
    }
}
