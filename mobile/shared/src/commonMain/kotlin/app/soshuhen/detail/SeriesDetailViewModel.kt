package app.soshuhen.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Resume
import app.soshuhen.api.Series
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.core.LocalStore
import app.soshuhen.ui.FAILED_FIRST
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.OFFLINE
import app.soshuhen.ui.UNREACHABLE
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch

data class DetailUi(val series: Series, val rows: List<ChapterRow>, val continueWith: ChapterRow?)

class SeriesDetailViewModel(
    private val seriesId: Long,
    private val api: StateFlow<SoshuhenApi?>,
    private val local: LocalStore,
) : ViewModel() {
    private val _state = MutableStateFlow<LoadState<DetailUi>>(LoadState.Loading)
    val state: StateFlow<LoadState<DetailUi>> = _state

    private var loading: Job? = null

    private fun ui(detail: SeriesDetail, resume: Resume?) =
        DetailUi(detail.series, chapterRows(detail), continueChapter(detail, resume))

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
                val json = client.seriesDetailJson(seriesId)
                val detail = SoshuhenJson.decodeFromString<SeriesDetail>(json)
                val resume = client.resume(seriesId)
                local.saveDetail(seriesId, json)
                LoadState.Loaded(ui(detail, resume))
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                if (previous is LoadState.Loaded) previous.copy(refreshFailed = UNREACHABLE)
                else local.detailSnapshot(seriesId)?.let { LoadState.Loaded(ui(it, null), refreshFailed = OFFLINE) }
                    ?: LoadState.Failed(FAILED_FIRST)
            }
        }
    }
}
