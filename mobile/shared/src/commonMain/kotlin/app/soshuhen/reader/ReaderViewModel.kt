package app.soshuhen.reader

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.ReaderPrefs
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.core.Availability
import app.soshuhen.core.ChapterFileMissing
import app.soshuhen.core.ChapterFolder
import app.soshuhen.core.ChapterRow
import app.soshuhen.core.DeviceChapter
import app.soshuhen.core.FolderUnavailable
import app.soshuhen.core.LocalStore
import app.soshuhen.core.Outbox
import app.soshuhen.core.chapterRows
import app.soshuhen.core.readableFrom
import app.soshuhen.ui.keep
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.math.floor

data class ReaderUi(
    val seriesId: Long,
    val chapter: ChapterRow,
    val source: PageSource,
    val pageCount: Int,
    val page: Int,
    val prefs: ReaderPrefs,
    val previous: Long?,
    val next: Long?,
    val chromeVisible: Boolean,
    // Every chapter of the series, newest first, for the chapter list; the
    // ones in [readable] are the ones that open from where the phone is.
    val chapters: List<ChapterRow> = emptyList(),
    val readable: Set<Long> = emptySet(),
)

sealed interface ReaderState {
    data object Loading : ReaderState
    data class Ready(val ui: ReaderUi) : ReaderState
    data class Unavailable(val message: String) : ReaderState
}

const val NOT_ON_DEVICE = "Not on this device. It will be copied the next time you are home."
const val FILE_MISSING = "This chapter's file is missing from the folder. It will be copied again at home."
const val FILE_UNREADABLE = "This chapter's file could not be read. It will be copied again at home."

// Only a chapter the server holds as a file is ever copied, so the promise in
// NOT_ON_DEVICE would be false for one it never downloaded.
const val NOT_DOWNLOADED = "Not downloaded on the server yet."

// Duplicated from the series screen on purpose: feature packages do not import
// from each other.
const val READER_FOLDER_GONE = "The chapters folder is not available. Pick it again in Settings."
const val SERVER_FAILED = "The server could not open this chapter."
const val OPEN_FAILED = "This chapter could not be opened."

// The server's own defaults, for a series opened away from home before its
// settings were ever fetched.
val DEFAULT_PREFS = ReaderPrefs("paged_rtl", "fit_screen", "black")

private const val POSITION_DELAY_MS = 1_000L

class ReaderViewModel(
    private val seriesId: Long,
    chapterId: Long,
    startPage: Int?,
    private val api: StateFlow<SoshuhenApi?>,
    private val atHome: StateFlow<Boolean>,
    private val local: LocalStore,
    private val folder: ChapterFolder,
    private val pages: PageExtractor,
    private val outbox: Outbox,
) : ViewModel() {
    private val _state = MutableStateFlow<ReaderState>(ReaderState.Loading)
    val state: StateFlow<ReaderState> = _state

    private var opening: Job? = null
    private var pendingPosition: Job? = null
    private var savePosition: (suspend () -> Unit)? = null

    // Once per open, as the web's: finishing a chapter twice in one sitting
    // would queue two completions for the server to replay.
    private var completed = false

    init {
        open(chapterId, startPage)
    }

    fun goTo(page: Int) {
        val ui = ready() ?: return
        val target = page.coerceIn(0, (ui.pageCount - 1).coerceAtLeast(0))
        _state.value = ReaderState.Ready(ui.copy(page = target))
        queuePosition(ui.chapter.id, target)
        val groups = spreads(ui.pageCount, ui.prefs.mode)
        if (groups.isNotEmpty() && target in groups.last()) finish(ui)
    }

    fun nextPage() {
        val ui = ready() ?: return
        val groups = spreads(ui.pageCount, ui.prefs.mode)
        val step = spreadOf(groups, ui.page)
        // Moving forward from the last spread is how a one-page chapter, which
        // opens already on its last page, gets finished at all.
        if (step + 1 < groups.size) goTo(groups[step + 1].first()) else if (groups.isNotEmpty()) finish(ui)
    }

    fun previousPage() {
        val ui = ready() ?: return
        val groups = spreads(ui.pageCount, ui.prefs.mode)
        val step = spreadOf(groups, ui.page)
        if (step > 0) goTo(groups[step - 1].first())
    }

    fun openChapter(id: Long) {
        // The page left behind is still news to the server; the new chapter's
        // first turn would otherwise cancel it.
        flushPosition()
        // A chapter picked from the list starts at its beginning, as the web's ?page=0.
        open(id, 0)
    }

    fun setPrefs(p: ReaderPrefs) {
        val ui = ready() ?: return
        _state.value = ReaderState.Ready(ui.copy(prefs = p))
        viewModelScope.launch {
            keep { local.savePrefs(seriesId, p) }
            keep { outbox.prefs(seriesId, p) }
            sendIfHome()
        }
    }

    fun toggleChrome() {
        val ui = ready() ?: return
        _state.value = ReaderState.Ready(ui.copy(chromeVisible = !ui.chromeVisible))
    }

    private fun ready(): ReaderUi? = (_state.value as? ReaderState.Ready)?.ui

    private fun open(chapterId: Long, startPage: Int?) {
        opening?.cancel()
        completed = false
        val chromeVisible = ready()?.chromeVisible ?: true
        _state.value = ReaderState.Loading
        opening = viewModelScope.launch {
            _state.value = try {
                load(chapterId, startPage, chromeVisible)
            } catch (e: CancellationException) {
                throw e
            } catch (_: FolderUnavailable) {
                ReaderState.Unavailable(READER_FOLDER_GONE)
            } catch (_: Exception) {
                // A database or provider failure is one chapter that will not
                // open, not a reason to take the whole app down.
                ReaderState.Unavailable(OPEN_FAILED)
            }
        }
    }

    private suspend fun load(chapterId: Long, startPage: Int?, chromeVisible: Boolean): ReaderState {
        // Decided once per open: a reader that switched source mid-chapter
        // because the Wi-Fi blinked would lose its place.
        val client = api.value.takeIf { atHome.value }
        val device = local.deviceChapters(seriesId).first()
        val rows = rows(client, device)
        val row = rows.firstOrNull { it.id == chapterId } ?: return ReaderState.Unavailable(NOT_ON_DEVICE)

        val opened: Pair<PageSource, Int?> = when {
            row.availability == Availability.OnDevice -> {
                val chapter = device.first { it.chapterId == chapterId }
                when (val found = fromDevice(chapter)) {
                    is DeviceOpen.Pages -> PageSource.Device(found.files) to null
                    is DeviceOpen.Lost -> return ReaderState.Unavailable(found.message)
                }
            }
            // Only a chapter the server holds as a file: a manifest for any
            // other would have the server fetch it from its source.
            client != null && row.availability == Availability.OnServer -> {
                val manifest = try {
                    client.manifest(chapterId)
                } catch (e: CancellationException) {
                    throw e
                } catch (_: Exception) {
                    return ReaderState.Unavailable(SERVER_FAILED)
                }
                PageSource.Server(client, chapterId, manifest.pageCount) to manifest.position
            }
            row.availability == Availability.NotDownloaded -> return ReaderState.Unavailable(NOT_DOWNLOADED)
            else -> return ReaderState.Unavailable(NOT_ON_DEVICE)
        }
        val (source, saved) = opened
        val pageCount = when (source) {
            is PageSource.Device -> source.pages.size
            is PageSource.Server -> source.pageCount
        }
        val readable = rows.filter { readableFrom(it, client != null) }
        return ReaderState.Ready(
            ReaderUi(
                seriesId = seriesId,
                chapter = row,
                source = source,
                pageCount = pageCount,
                page = (startPage ?: saved ?: 0).coerceIn(0, (pageCount - 1).coerceAtLeast(0)),
                prefs = prefs(client),
                previous = readable.filter { it.number < row.number }.maxByOrNull { it.number }?.id,
                next = readable.filter { it.number > row.number }.minByOrNull { it.number }?.id,
                chromeVisible = chromeVisible,
                chapters = rows.sortedByDescending { it.number },
                readable = readable.map { it.id }.toSet(),
            ),
        )
    }

    private sealed interface DeviceOpen {
        class Pages(val files: List<okio.Path>) : DeviceOpen
        class Lost(val message: String) : DeviceOpen
    }

    private suspend fun fromDevice(chapter: DeviceChapter): DeviceOpen {
        val source = try {
            if (!folder.exists(chapter.uri)) null else folder.read(chapter.uri)
        } catch (_: ChapterFileMissing) {
            null
        } ?: return forget(chapter, FILE_MISSING)
        // Closed here on every path: on a cache hit ZipPages never touches the
        // source, and each one left open is a file descriptor held by SAF.
        return try {
            DeviceOpen.Pages(source.use { pages.extract(chapter.chapterId, it) })
        } catch (e: CancellationException) {
            throw e
        } catch (e: FolderUnavailable) {
            throw e
        } catch (_: Exception) {
            // A cut-off or corrupt archive: the copy is what is broken, and
            // the next import replaces it once the index no longer holds it.
            forget(chapter, FILE_UNREADABLE)
        }
    }

    // Forgotten so the next import at home sees the chapter missing and copies it again.
    private suspend fun forget(chapter: DeviceChapter, message: String): DeviceOpen {
        local.forgetChapter(chapter.chapterId)
        return DeviceOpen.Lost(message)
    }

    private suspend fun rows(client: SoshuhenApi?, device: List<DeviceChapter>): List<ChapterRow> {
        val onDevice = device.map { it.chapterId }.toSet()
        val detail = client?.let { fetchDetail(it) } ?: local.detailSnapshot(seriesId)
        val listed = detail?.let { chapterRows(it, onDevice) }.orEmpty()
        val ids = listed.map { it.id }.toSet()
        // A chapter copied before the series was ever opened online has no
        // snapshot behind it, and is still the user's to read.
        val unlisted = device.filter { it.chapterId !in ids }.map {
            ChapterRow(it.chapterId, it.number, title = null, read = false, availability = Availability.OnDevice)
        }
        return listed + unlisted
    }

    private suspend fun fetchDetail(client: SoshuhenApi): SeriesDetail? = try {
        val json = client.seriesDetailJson(seriesId)
        SoshuhenJson.decodeFromString<SeriesDetail>(json).also { keep { local.saveDetail(seriesId, json) } }
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        null
    }

    private suspend fun prefs(client: SoshuhenApi?): ReaderPrefs {
        if (client != null) {
            try {
                return client.prefs(seriesId).also { keep { local.savePrefs(seriesId, it) } }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
            }
        }
        return local.prefsSnapshot(seriesId) ?: DEFAULT_PREFS
    }

    // Debounced like the web's usePositionSaver: a flick through ten pages is
    // one position, not ten rows replacing each other.
    private fun queuePosition(chapterId: Long, page: Int) {
        pendingPosition?.cancel()
        // A failed write loses this one position; the next turn writes another.
        val save: suspend () -> Unit = {
            keep { outbox.position(seriesId, chapterId, page) }
            sendIfHome()
        }
        savePosition = save
        pendingPosition = viewModelScope.launch {
            delay(POSITION_DELAY_MS)
            savePosition = null
            save()
        }
    }

    private fun flushPosition() {
        val save = savePosition ?: return
        pendingPosition?.cancel()
        savePosition = null
        viewModelScope.launch { save() }
    }

    private fun finish(ui: ReaderUi) {
        if (completed) return
        completed = true
        viewModelScope.launch {
            keep { outbox.complete(seriesId, ui.chapter.id) }
            keep { local.raiseProgress(seriesId, floor(ui.chapter.number).toInt()) }
            sendIfHome()
        }
    }

    // A phone that never leaves the house would otherwise hold its reading
    // until the next import run.
    private suspend fun sendIfHome() {
        val client = api.value ?: return
        if (!atHome.value) return
        keep { outbox.drain(client) }
    }
}
