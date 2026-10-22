package app.soshuhen.reader

import app.soshuhen.core.ArchiveCheck
import app.soshuhen.core.NoRoomForPages
import app.soshuhen.core.PageExtractor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okio.FileSystem
import okio.Path
import okio.Source
import okio.buffer
import okio.sink
import okio.source
import java.util.zip.ZipInputStream

/**
 * Pages out of a chapter's CBZ, extracted once into the app's own cache.
 * A reader asks for page n many times; unzipping on each ask would read the
 * whole archive again every swipe. The cache is never the user's folder.
 */
class ZipPages(
    private val cacheDir: Path,
    private val fileSystem: FileSystem = FileSystem.SYSTEM,
) : ArchiveCheck, PageExtractor {
    private val root = cacheDir / "reader"
    private val lock = Mutex()

    override suspend fun extract(chapterId: Long, version: String, source: Source): List<Path> = lock.withLock {
        withContext(Dispatchers.IO) {
            val dir = root / chapterId.toString()
            val done = dir / DONE
            val from = dir / FROM
            // A directory with no marker is an extraction that died halfway;
            // reusing it would serve a chapter with pages missing. One made from
            // another copy of the archive would serve the old copy's pages.
            val current = fileSystem.exists(done) && fileSystem.exists(from) &&
                fileSystem.read(from) { readUtf8() } == version
            if (!current) {
                fileSystem.deleteRecursively(dir)
                write(dir, source)
                cache { fileSystem.write(from) { writeUtf8(version) } }
            }
            cache { mark(dir) }
            prune(keep = dir)
            pagesIn(dir)
        }
    }

    override suspend fun pageCount(source: Source): Int = withContext(Dispatchers.IO) {
        var count = 0
        val scratch = ByteArray(DRAIN_BUFFER)
        ZipInputStream(source.buffer().inputStream()).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (isPage(entry.name)) {
                    // Draining is what notices a cut-off archive: a header alone
                    // reads fine, only the data after it runs out.
                    // A plain loop: OutputStream.nullOutputStream() is API 33 and
                    // minSdk is 29, where it would throw an Error, not an Exception.
                    while (zip.read(scratch) != -1) continue
                    count++
                }
            }
        }
        count
    }

    private fun write(dir: Path, source: Source) {
        cache { fileSystem.createDirectories(dir) }
        // The zip is streamed once in archive order, but the server numbers pages
        // in natural order, which is only known after the last entry.
        val written = mutableListOf<Pair<String, Path>>()
        ZipInputStream(source.buffer().inputStream()).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (!isPage(entry.name)) continue
                val temp = dir / "part-${written.size}"
                cache { fileSystem.sink(temp).buffer() }.use { out ->
                    // Read and write apart, so a failing read blames the
                    // archive and a failing write blames the cache.
                    val chunk = ByteArray(DRAIN_BUFFER)
                    while (true) {
                        val n = zip.read(chunk)
                        if (n == -1) break
                        cache { out.write(chunk, 0, n) }
                    }
                    cache { out.flush() }
                }
                written += entry.name to temp
            }
        }
        val order = pageOrder(written.map { it.first })
        val byName = written.toMap()
        order.forEachIndexed { index, name ->
            val extension = name.substringAfterLast('.').lowercase()
            cache { fileSystem.atomicMove(byName.getValue(name), dir / "$index.$extension") }
        }
    }

    // The app's cache failing to take the pages, which is no fault of the
    // chapter's file: the reader keeps the chapter and says why it will not open.
    private inline fun <T> cache(block: () -> T): T = try {
        block()
    } catch (e: java.io.IOException) {
        throw NoRoomForPages(e)
    }

    private fun mark(dir: Path) {
        val newest = chapters().maxOfOrNull { sequence(it) } ?: 0L
        fileSystem.write(dir / DONE) { writeUtf8((newest + 1).toString()) }
    }

    private fun prune(keep: Path) {
        val recent = chapters().sortedByDescending { sequence(it) }
        for (stale in recent.drop(KEPT)) if (stale != keep) fileSystem.deleteRecursively(stale)
    }

    private fun chapters(): List<Path> =
        if (fileSystem.exists(root)) {
            fileSystem.list(root).filter { fileSystem.exists(it / DONE) }
        } else {
            emptyList()
        }

    private fun sequence(dir: Path): Long =
        fileSystem.read(dir / DONE) { readUtf8() }.toLongOrNull() ?: 0L

    private fun pagesIn(dir: Path): List<Path> =
        fileSystem.list(dir)
            .filter { !it.name.startsWith(".") && !it.name.startsWith("part-") }
            .sortedBy { it.name.substringBefore('.').toInt() }

    private companion object {
        const val DONE = ".done"
        // Which copy of the archive the pages came from.
        const val FROM = ".from"
        const val DRAIN_BUFFER = 8192
        // The reader moves between neighbouring chapters; a few cover that
        // without a long read filling the phone's storage.
        const val KEPT = 5
    }
}
