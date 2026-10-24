package app.soshuhen.reader

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.SoshuhenJson
import app.soshuhen.core.BookExtractor
import app.soshuhen.core.BookKind
import app.soshuhen.core.BookRef
import app.soshuhen.core.ChapterFileMissing
import app.soshuhen.core.ChapterFolder
import app.soshuhen.core.FolderUnavailable
import app.soshuhen.core.LocalStore
import app.soshuhen.core.NOT_DOWNLOADED
import app.soshuhen.core.NOT_ON_DEVICE
import app.soshuhen.core.NoRoomForPages
import app.soshuhen.core.Outbox
import app.soshuhen.ui.keep
import io.ktor.utils.io.readAvailable
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okio.FileSystem
import okio.Path
import kotlin.math.floor

data class ProseUi(
    val seriesId: Long,
    val ref: BookRef,
    val title: String,
    val book: Book,
    val position: ProsePosition,
    val mode: String,
    val style: ProseStyle,
    val previous: BookRef?,
    val next: BookRef?,
    val chromeVisible: Boolean,
)

sealed interface ProseState {
    data object Loading : ProseState
    data class Ready(val ui: ProseUi) : ProseState
    data class Unavailable(val message: String) : ProseState
}

private const val POSITION_DELAY_MS = 1_000L

/** One readable item of a novel, chapter or light volume, as the reader needs to know it. */
private class Item(val ref: BookRef, val number: Double, val title: String, val onServer: Boolean)

/**
 * The prose reader's state. It shares the manga reader's rules for where a
 * book opens from (the device always, the server only at home) and for
 * finishing (once per open), and keeps its place on the device.
 */
class ProseReaderViewModel(
    private val seriesId: Long,
    ref: BookRef,
    private val api: StateFlow<SoshuhenApi?>,
    private val atHome: StateFlow<Boolean>,
    private val local: LocalStore,
    private val folder: ChapterFolder,
    private val books: BookExtractor,
    private val outbox: Outbox,
    private val cacheDir: Path,
    private val fs: FileSystem = FileSystem.SYSTEM,
) : ViewModel() {
    private val _state = MutableStateFlow<ProseState>(ProseState.Loading)
    val state: StateFlow<ProseState> = _state
    private val prose = ProseStore(local)

    private var opening: Job? = null
    private var pendingPosition: Job? = null
    private var savePosition: (suspend () -> Unit)? = null
    private var completed = false
    private var number = 0.0

    init {
        open(ref)
    }

    private fun ready(): ProseUi? = (_state.value as? ProseState.Ready)?.ui

    fun moveTo(p: ProsePosition) {
        val ui = ready() ?: return
        if (p == ui.position) return
        _state.value = ProseState.Ready(ui.copy(position = p))
        pendingPosition?.cancel()
        val save: suspend () -> Unit = { keep { prose.savePosition(ui.ref, p) } }
        savePosition = save
        // Debounced as the manga reader's: a flick through ten pages is one write.
        pendingPosition = viewModelScope.launch {
            delay(POSITION_DELAY_MS)
            savePosition = null
            save()
        }
    }

    fun finish() {
        val ui = ready() ?: return
        if (completed) return
        completed = true
        val whole = floor(number).toInt()
        viewModelScope.launch {
            when (ui.ref.kind) {
                BookKind.Chapter -> {
                    keep { outbox.complete(seriesId, ui.ref.id) }
                    keep { local.raiseProgress(seriesId, whole) }
                }
                BookKind.Volume -> {
                    keep { outbox.completeVolume(seriesId, ui.ref.id) }
                    keep { local.raiseVolumeProgress(seriesId, whole) }
                }
            }
            sendIfHome()
        }
    }

    fun setMode(mode: String) {
        val ui = ready() ?: return
        _state.value = ProseState.Ready(ui.copy(mode = mode))
        viewModelScope.launch { keep { prose.saveMode(seriesId, mode) } }
    }

    fun setStyle(style: ProseStyle) {
        val ui = ready() ?: return
        _state.value = ProseState.Ready(ui.copy(style = style))
        viewModelScope.launch { keep { prose.saveStyle(style) } }
    }

    fun toggleChrome() {
        val ui = ready() ?: return
        _state.value = ProseState.Ready(ui.copy(chromeVisible = !ui.chromeVisible))
    }

    fun open(ref: BookRef) {
        // The place left behind would otherwise be lost to the new book's first move.
        savePosition?.let { save ->
            pendingPosition?.cancel()
            savePosition = null
            viewModelScope.launch { save() }
        }
        opening?.cancel()
        completed = false
        val chromeVisible = ready()?.chromeVisible ?: true
        _state.value = ProseState.Loading
        opening = viewModelScope.launch {
            _state.value = try {
                load(ref, chromeVisible)
            } catch (e: CancellationException) {
                throw e
            } catch (_: FolderUnavailable) {
                ProseState.Unavailable(READER_FOLDER_GONE)
            } catch (_: Exception) {
                ProseState.Unavailable(OPEN_FAILED)
            }
        }
    }

    private suspend fun load(ref: BookRef, chromeVisible: Boolean): ProseState {
        // Decided once per open, as the manga reader does.
        val client = api.value.takeIf { atHome.value }
        val detail = client?.let { fetchDetail(it) } ?: local.detailSnapshot(seriesId)
        val items = detail?.let { items(it, ref.kind) }.orEmpty()
        val item = items.firstOrNull { it.ref == ref }
        val onDevice = onDevice(ref)
        number = item?.number ?: onDevice?.number ?: 0.0

        val dir = when {
            onDevice != null -> when (val found = fromDevice(ref, onDevice)) {
                is Opened.Dir -> found.path
                is Opened.Lost -> return ProseState.Unavailable(found.message)
            }
            client != null && item?.onServer == true -> fromServer(client, ref) ?: return ProseState.Unavailable(SERVER_FAILED)
            item != null && !item.onServer -> return ProseState.Unavailable(NOT_DOWNLOADED)
            else -> return ProseState.Unavailable(NOT_ON_DEVICE)
        }
        val book = try {
            readBook(fs, dir)
        } catch (_: NotAnEpub) {
            if (onDevice != null) markUnreadable(ref)
            return ProseState.Unavailable(FILE_UNREADABLE)
        }

        val readable = items.filter { it.ref == ref || it.onServer && client != null || isOnDevice(it.ref) }
        val title = item?.title ?: defaultTitle(ref.kind, number)
        return ProseState.Ready(
            ProseUi(
                seriesId = seriesId,
                ref = ref,
                title = title,
                book = book,
                position = book.clamp(prose.position(ref) ?: ProsePosition(0, 0, 0)),
                mode = prose.mode(seriesId) ?: DEFAULT_PROSE_MODE,
                style = prose.style(),
                previous = readable.filter { it.number < number }.maxByOrNull { it.number }?.ref,
                next = readable.filter { it.number > number }.minByOrNull { it.number }?.ref,
                chromeVisible = chromeVisible,
            ),
        )
    }

    private class Held(val number: Double, val uri: String, val etag: String?, val size: Long)

    private suspend fun onDevice(ref: BookRef): Held? = when (ref.kind) {
        BookKind.Chapter -> local.deviceChapter(ref.id)?.let { Held(it.number, it.uri, it.etag, it.size) }
        BookKind.Volume -> local.deviceVolume(ref.id)?.let { Held(it.number, it.uri, it.etag, it.size) }
    }

    private suspend fun isOnDevice(ref: BookRef) = onDevice(ref) != null

    private sealed interface Opened {
        class Dir(val path: Path) : Opened
        class Lost(val message: String) : Opened
    }

    private suspend fun fromDevice(ref: BookRef, held: Held): Opened {
        val source = try {
            if (!folder.exists(held.uri)) null else folder.read(held.uri)
        } catch (_: ChapterFileMissing) {
            null
        }
        if (source == null) {
            // Forgotten so the next import at home copies it again.
            when (ref.kind) {
                BookKind.Chapter -> local.forgetChapter(ref.id)
                BookKind.Volume -> local.forgetVolume(ref.id)
            }
            return Opened.Lost(FILE_MISSING)
        }
        return try {
            Opened.Dir(source.use { books.unpack(ref, "${held.etag}:${held.size}", it) })
        } catch (e: CancellationException) {
            throw e
        } catch (e: FolderUnavailable) {
            throw e
        } catch (_: NoRoomForPages) {
            Opened.Lost(NO_ROOM)
        } catch (_: Exception) {
            markUnreadable(ref)
            Opened.Lost(FILE_UNREADABLE)
        }
    }

    private suspend fun markUnreadable(ref: BookRef) = keep {
        when (ref.kind) {
            BookKind.Chapter -> local.markUnreadable(ref.id)
            BookKind.Volume -> local.markVolumeUnreadable(ref.id)
        }
    }

    /**
     * A book the server holds and the device does not, read at home: fetched
     * whole into the cache and unpacked there. The picked folder is the
     * import's alone, so nothing is written to it from here.
     */
    private suspend fun fromServer(client: SoshuhenApi, ref: BookRef): Path? {
        val download = cacheDir / "download-${ref.kind.key}-${ref.id}.epub"
        return try {
            val read: suspend (app.soshuhen.api.ArchiveDownload) -> String? = { d ->
                fs.write(download) {
                    val bytes = ByteArray(64 * 1024)
                    while (true) {
                        val n = d.body.readAvailable(bytes, 0, bytes.size)
                        if (n == -1) break
                        write(bytes, 0, n)
                    }
                }
                d.etag
            }
            val etag = when (ref.kind) {
                BookKind.Chapter -> client.archive(ref.id, 0, read = read)
                BookKind.Volume -> client.volumeArchive(ref.id, 0, read = read)
            }
            fs.source(download).use { books.unpack(ref, "server:$etag", it) }
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            null
        } finally {
            fs.delete(download, mustExist = false)
        }
    }

    private suspend fun fetchDetail(client: SoshuhenApi): SeriesDetail? = try {
        val json = client.seriesDetailJson(seriesId)
        SoshuhenJson.decodeFromString<SeriesDetail>(json).also { keep { local.saveDetail(seriesId, json) } }
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        null
    }

    private fun items(detail: SeriesDetail, kind: BookKind): List<Item> = when (kind) {
        BookKind.Chapter -> detail.chapters.map {
            Item(
                BookRef(BookKind.Chapter, it.id), it.number,
                it.title ?: defaultTitle(BookKind.Chapter, it.number),
                onServer = it.state == "downloaded" && it.filePath != null,
            )
        }
        // Light volumes only: a web volume is read through its chapters.
        BookKind.Volume -> detail.volumes.filter { it.edition == "light" && it.id != null }.map {
            Item(
                BookRef(BookKind.Volume, it.id!!), it.number,
                it.title?.let { t -> "${defaultTitle(BookKind.Volume, it.number)}: $t" } ?: defaultTitle(BookKind.Volume, it.number),
                onServer = it.readable,
            )
        }
    }

    private fun defaultTitle(kind: BookKind, number: Double): String {
        val shown = if (number % 1.0 == 0.0) number.toLong().toString() else number.toString()
        return if (kind == BookKind.Volume) "Volume $shown" else "Chapter $shown"
    }

    // A phone that never leaves the house would otherwise hold its reading until the next import.
    private suspend fun sendIfHome() {
        val client = api.value ?: return
        if (!atHome.value) return
        keep { outbox.drain(client) }
    }
}
