package app.soshuhen.profiles

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Profile
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.api.key
import app.soshuhen.core.LocalStore
import app.soshuhen.core.ServerStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ProfilesState(
    val profiles: List<Profile> = emptyList(),
    val loaded: Boolean = false,
    val atHome: Boolean = false,
    /** The profile whose PIN pad is open, if any. */
    val pinFor: Profile? = null,
    val pinError: Boolean = false,
    val busy: Boolean = false,
)

/** The picker, the PIN pad, and which profile the app opens as. */
class ProfilesViewModel(
    private val api: StateFlow<SoshuhenApi?>,
    private val atHome: StateFlow<Boolean>,
    private val store: ServerStore,
    private val local: LocalStore,
) : ViewModel() {
    private val _state = MutableStateFlow(ProfilesState())
    val state: StateFlow<ProfilesState> = _state

    // In memory only: a cold start is exactly when the picker should ask again.
    private val chosen = MutableStateFlow(false)
    private val switching = MutableStateFlow(false)

    val route: StateFlow<StartRoute> = combine(
        _state, store.profileKey, chosen, switching,
    ) { state, saved, chosen, switching ->
        startRoute(state.profiles.takeIf { state.loaded }, state.atHome, saved, chosen, switching)
    }.stateIn(viewModelScope, SharingStarted.Eagerly, StartRoute.Open(0))

    init {
        viewModelScope.launch {
            atHome.combine(api) { home, client -> home to client }
                .distinctUntilChanged()
                .collect { (home, client) -> load(home, client) }
        }
    }

    private suspend fun load(home: Boolean, client: SoshuhenApi?) {
        val fromServer = if (home && client != null) {
            try {
                val json = client.profilesJson()
                local.putProfiles(json)
                SoshuhenJson.decodeFromString<List<Profile>>(json)
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                null
            }
        } else {
            null
        }
        val profiles = fromServer ?: local.profilesSnapshot()
        _state.update {
            it.copy(
                profiles = profiles.orEmpty().sortedWith(compareBy({ p -> p.position }, { p -> p.id })),
                loaded = profiles != null,
                atHome = home && fromServer != null,
            )
        }
    }

    fun choose(profile: Profile) {
        if (!profile.hasPin) {
            open(profile)
            return
        }
        // Only the server can check a PIN; away from it, a PIN profile stays shut.
        if (!_state.value.atHome) return
        _state.update { it.copy(pinFor = profile, pinError = false) }
    }

    fun submitPin(pin: String) {
        val profile = _state.value.pinFor ?: return
        val client = api.value ?: return
        _state.update { it.copy(busy = true) }
        viewModelScope.launch {
            val ok = try {
                client.unlock(profile.id, pin)
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                false
            }
            _state.update { it.copy(busy = false, pinError = !ok) }
            if (ok) open(profile)
        }
    }

    fun cancelPin() = _state.update { it.copy(pinFor = null, pinError = false) }

    /** Settings' "Switch profile": back to the picker, wherever the phone is. */
    fun switchProfile() {
        switching.value = true
    }

    private fun open(profile: Profile) {
        viewModelScope.launch {
            store.selectProfile(profile.key())
            chosen.value = true
            switching.value = false
            _state.update { it.copy(pinFor = null, pinError = false) }
        }
    }
}
