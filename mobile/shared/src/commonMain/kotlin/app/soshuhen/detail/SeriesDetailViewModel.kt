package app.soshuhen.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Series
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.ui.FAILED_FIRST
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.UNREACHABLE
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

data class DetailUi(val series: Series, val rows: List<ChapterRow>, val continueWith: ChapterRow?)

class SeriesDetailViewModel(
    private val seriesId: Long,
    private val api: StateFlow<SoshuhenApi?>,
) : ViewModel() {
    private val _state = MutableStateFlow<LoadState<DetailUi>>(LoadState.Loading)
    val state: StateFlow<LoadState<DetailUi>> = _state

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val client = api.filterNotNull().first()
            val previous = _state.value
            _state.value = try {
                val detail = client.seriesDetail(seriesId)
                val resume = client.resume(seriesId)
                LoadState.Loaded(DetailUi(detail.series, chapterRows(detail), continueChapter(detail, resume)))
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                if (previous is LoadState.Loaded) previous.copy(refreshFailed = UNREACHABLE)
                else LoadState.Failed(FAILED_FIRST)
            }
        }
    }
}
