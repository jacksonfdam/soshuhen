package app.soshuhen.detail

import app.soshuhen.core.ChapterRow
import app.soshuhen.core.chapterRows
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.Resume
import app.soshuhen.api.Series
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SeriesMetadata
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.core.DeviceChapter
import app.soshuhen.core.DeviceLibrary
import app.soshuhen.core.DeviceVolume
import app.soshuhen.core.volumesRead
import app.soshuhen.core.FolderUnavailable
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
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlin.math.floor
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch

data class DetailUi(
    val series: Series,
    val rows: List<ChapterRow>,
    val continueWith: ChapterRow?,
    // The server's resume page when Continue is that chapter; null leaves the
    // reader to find the chapter's own saved place.
    val continuePage: Int?,
    val marked: Boolean,
    val deviceChapters: Int,
    val readOnDevice: Int,
    // Read straight through from the server for the header and progress card.
    val metadata: SeriesMetadata = SeriesMetadata(),
    val minutesPerChapter: Int? = null,
    // A novel's volumes and web chapters by edition; null for a comic.
    val prose: ProseRows? = null,
    val continueVolume: VolumeRow? = null,
)

/** What the server said, before the device's own state is laid over it. */
private class Remote(val detail: SeriesDetail, val resume: Resume?, val volumeProgress: Int?)

const val FOLDER_GONE = "The chapters folder is not available. Pick it again in Settings."

class SeriesDetailViewModel(
    private val seriesId: Long,
    private val api: StateFlow<SoshuhenApi?>,
    private val atHome: StateFlow<Boolean>,
    private val local: LocalStore,
    private val library: DeviceLibrary,
) : ViewModel() {
    private val remote = MutableStateFlow<LoadState<Remote>>(LoadState.Loading)

    // Marking and the device's files change under a loaded screen, so they are
    // laid over what the server said instead of being baked into it.
    val state: StateFlow<LoadState<DetailUi>> = combine(
        remote, local.isMarked(seriesId), local.deviceChapters(seriesId), local.deviceVolumes(seriesId),
    ) { loaded, marked, onDevice, volumes ->
        when (loaded) {
            LoadState.Loading -> LoadState.Loading
            is LoadState.Failed -> loaded
            is LoadState.Loaded -> LoadState.Loaded(ui(loaded.data, marked, onDevice, volumes), loaded.refreshFailed)
        }
    }.stateIn(viewModelScope, SharingStarted.Eagerly, LoadState.Loading)

    private val chosenEdition = MutableStateFlow<String?>(null)

    /** Which of a novel's editions the list shows: the user's pick, else the default for the series. */
    val edition: StateFlow<String> = combine(chosenEdition, state) { chosen, loaded ->
        chosen ?: (loaded as? LoadState.Loaded)?.data?.prose?.let(::defaultEdition) ?: LIGHT
    }.stateIn(viewModelScope, SharingStarted.Eagerly, LIGHT)

    fun setEdition(edition: String) { chosenEdition.value = edition }

    private val _unmarkPrompt = MutableStateFlow<Int?>(null)

    /** The number of chapters on the device while the unmark question is open, null otherwise. */
    val unmarkPrompt: StateFlow<Int?> = _unmarkPrompt

    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice

    private var loading: Job? = null
    private var lastDetail: SeriesDetail? = null

    private fun ui(remote: Remote, marked: Boolean, onDevice: List<DeviceChapter>, volumes: List<DeviceVolume>): DetailUi {
        val ids = onDevice.map { it.chapterId }.toSet()
        val series = remote.detail.series
        val next = continueChapter(remote.detail, remote.resume, ids)
        val prose = if (series.kind == "prose") {
            proseRows(remote.detail, ids, volumes.map { it.volumeId }.toSet(), remote.volumeProgress)
        } else {
            null
        }
        val volumesRead = volumesRead(remote.detail, remote.volumeProgress)
        return DetailUi(
            series, chapterRows(remote.detail, ids), next,
            remote.resume?.takeIf { it.chapterId == next?.id }?.page,
            marked,
            onDevice.size + volumes.size,
            onDevice.count { floor(it.number) <= series.progress } + volumes.count { floor(it.number) <= volumesRead },
            remote.detail.metadata, remote.detail.readingMinutesPerChapter,
            prose, prose?.let(::continueVolume),
        )
    }

    /** The switch. Turning it off with chapters on the device asks first. */
    fun setMarked(on: Boolean) {
        val series = (state.value as? LoadState.Loaded)?.data?.series ?: return
        viewModelScope.launch {
            if (on) {
                library.mark(series)
                return@launch
            }
            val count = (state.value as? LoadState.Loaded)?.data?.deviceChapters ?: 0
            if (count > 0) _unmarkPrompt.value = count else library.unmark(seriesId, deleteFiles = false)
        }
    }

    fun unmark(deleteFiles: Boolean) {
        _unmarkPrompt.value = null
        attempt { library.unmark(seriesId, deleteFiles) }
    }

    fun dismissUnmark() { _unmarkPrompt.value = null }

    fun deleteChapter(chapterId: Long) = attempt { library.deleteChapter(chapterId) }

    fun deleteVolume(volumeId: Long) = attempt { library.deleteVolume(volumeId) }

    fun deleteRead() {
        val detail = lastDetail ?: return
        attempt { library.deleteRead(detail) }
    }

    fun dismissNotice() { _notice.value = null }

    private fun attempt(action: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                action()
            } catch (e: CancellationException) {
                throw e
            } catch (_: FolderUnavailable) {
                _notice.value = FOLDER_GONE
            }
        }
    }

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
            val previous = remote.value
            remote.value = try {
                val json = client.seriesDetailJson(seriesId)
                val detail = SoshuhenJson.decodeFromString<SeriesDetail>(json)
                keep { local.saveDetail(seriesId, json) }
                lastDetail = detail
                LoadState.Loaded(Remote(detail, local.queuedPosition(seriesId) ?: serverResume(client), local.volumeProgress(seriesId)))
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                if (previous is LoadState.Loaded) previous.copy(refreshFailed = refreshFailure())
                else local.detailSnapshot(seriesId)?.let {
                    lastDetail = it
                    LoadState.Loaded(Remote(it, local.resume(seriesId), local.volumeProgress(seriesId)), refreshFailed = OFFLINE)
                }
                    ?: LoadState.Failed(FAILED_FIRST)
            }
        }
    }

    // Only where to continue: a resume the server failed to give must not throw
    // away a detail that loaded, so the device's last known place stands in.
    private suspend fun serverResume(client: SoshuhenApi): Resume? = try {
        client.resume(seriesId).also { keep { local.saveResume(seriesId, it) } }
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        local.resume(seriesId)
    }

    // Away from home the server is not down, it is simply not there: the same
    // words as a cold start offline, not a second wording for one situation.
    private fun refreshFailure() = if (atHome.value) UNREACHABLE else OFFLINE
}
