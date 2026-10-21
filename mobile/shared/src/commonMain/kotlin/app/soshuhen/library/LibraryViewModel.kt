package app.soshuhen.library

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Series
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.core.LocalStore
import app.soshuhen.ui.FAILED_FIRST
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.OFFLINE
import app.soshuhen.ui.keep
import app.soshuhen.ui.UNREACHABLE
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch

class LibraryViewModel(
    private val api: StateFlow<SoshuhenApi?>,
    private val local: LocalStore,
    atHome: StateFlow<Boolean>,
) : ViewModel() {
    val atHome: StateFlow<Boolean> = atHome

    /** The series kept on this device. */
    val marked: StateFlow<Set<Long>> = local.markedIds()
        .stateIn(viewModelScope, SharingStarted.Eagerly, emptySet())

    private val _state = MutableStateFlow<LoadState<List<Series>>>(LoadState.Loading)
    val state: StateFlow<LoadState<List<Series>>> = _state
    private val _status = MutableStateFlow<String?>("reading")
    val status: StateFlow<String?> = _status
    private val _query = MutableStateFlow("")
    val query: StateFlow<String> = _query

    private var loading: Job? = null

    init {
        // Every address the session settles on, not only the first: when the
        // server turns up somewhere new, the screen follows it without a tap.
        viewModelScope.launch {
            api.filterNotNull().distinctUntilChanged().collect { load(it) }
        }
    }

    fun refresh() {
        api.value?.let { load(it) }
    }

    private fun load(client: SoshuhenApi) {
        // One request at a time, so a slow old answer cannot land on a new one.
        loading?.cancel()
        loading = viewModelScope.launch {
            val previous = _state.value
            _state.value = try {
                val json = client.seriesJson()
                val rows = SoshuhenJson.decodeFromString<List<Series>>(json)
                keep { local.saveSeries(json) }
                LoadState.Loaded(comics(rows))
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                // Over loaded data a failure is a banner, not a blank screen:
                // the laptop went to sleep, the library did not vanish.
                if (previous is LoadState.Loaded) previous.copy(refreshFailed = UNREACHABLE)
                else local.seriesSnapshot()?.let { LoadState.Loaded(comics(it), refreshFailed = OFFLINE) }
                    ?: LoadState.Failed(FAILED_FIRST)
            }
        }
    }

    fun setStatus(status: String?) { _status.value = status }

    fun setQuery(query: String) { _query.value = query }
}
