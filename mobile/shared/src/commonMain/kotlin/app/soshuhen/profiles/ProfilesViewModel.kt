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
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
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

/**
 * How long a cold start waits for the location check before treating the
 * phone as away. A scan of a strange network can take far longer, and a
 * reader on a train should not stare at a blank screen for it.
 */
const val DECIDE_TIMEOUT_MS = 3_000L

/** The picker, the PIN pad, and which profile the app opens as. */
class ProfilesViewModel(
    private val api: StateFlow<SoshuhenApi?>,
    private val atHome: StateFlow<Boolean>,
    // True once the session has answered "home or away" for the first time.
    private val located: StateFlow<Boolean>,
    // The key the session's API and the device store actually read with.
    private val sessionKey: StateFlow<Long>,
    private val store: ServerStore,
    private val local: LocalStore,
) : ViewModel() {
    private val _state = MutableStateFlow(ProfilesState())
    val state: StateFlow<ProfilesState> = _state

    // In memory only: a cold start is exactly when the picker should ask again.
    private val chosen = MutableStateFlow(false)
    private val switching = MutableStateFlow(false)

    private val timedOut = MutableStateFlow(false)

    // Until both are known, nothing opens: a shell drawn before the location
    // check answered showed the last person's library to whoever picked the
    // tablet up, and one drawn before the session read the saved key read
    // everything as the manager.
    private val decided = combine(located, timedOut) { known, late -> known || late }

    val route: StateFlow<StartRoute> = combine(
        combine(_state, store.profileKey, chosen, switching) { state, saved, chosen, switching ->
            Triple(state, saved, chosen to switching)
        },
        decided,
        sessionKey,
    ) { (state, saved, flags), decided, session ->
        if (!decided) return@combine StartRoute.Deciding
        val route = startRoute(state.profiles.takeIf { state.loaded }, state.atHome, saved, flags.first, flags.second)
        if (route is StartRoute.Open && route.key != session) StartRoute.Deciding else route
    }.stateIn(viewModelScope, SharingStarted.Eagerly, StartRoute.Deciding)

    init {
        viewModelScope.launch {
            delay(DECIDE_TIMEOUT_MS)
            timedOut.value = true
        }
        viewModelScope.launch {
            atHome.combine(api) { home, client -> home to client }
                .distinctUntilChanged()
                .collect { (home, client) -> load(home, client) }
        }
    }

    private suspend fun load(home: Boolean, client: SoshuhenApi?) {
        val fromServer = if (home && client != null) {
            try {
                // Asked as nobody: a saved profile the server deleted would
                // have this refused, and the list is how the app recovers.
                val json = client.forProfile(0).profilesJson()
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
        // A saved profile the server no longer lists was deleted: forget it, so
        // the session stops naming it and the picker (or the manager) takes over.
        if (fromServer != null) {
            val saved = store.profileKey.first()
            if (saved != null && fromServer.none { it.key() == saved }) store.selectProfile(null)
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
        // The error clears as the check starts, so a second wrong PIN is a new
        // error the pad reacts to, not the same one it already showed.
        _state.update { it.copy(busy = true, pinError = false) }
        viewModelScope.launch {
            val ok = try {
                client.forProfile(0).unlock(profile.id, pin)
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
