package app.soshuhen.reader

import app.soshuhen.core.ArchiveCheck
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

    override suspend fun extract(chapterId: Long, source: Source): List<Path> = lock.withLock {
        withContext(Dispatchers.IO) {
            val dir = root / chapterId.toString()
            val done = dir / DONE
            if (!fileSystem.exists(done)) {
                // A directory with no marker is an extraction that died halfway;
                // reusing it would serve a chapter with pages missing.
                fileSystem.deleteRecursively(dir)
                write(dir, source)
            }
            mark(dir)
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
        fileSystem.createDirectories(dir)
        // The zip is streamed once in archive order, but the server numbers pages
        // in natural order, which is only known after the last entry.
        val written = mutableListOf<Pair<String, Path>>()
        ZipInputStream(source.buffer().inputStream()).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (!isPage(entry.name)) continue
                val temp = dir / "part-${written.size}"
                fileSystem.sink(temp).buffer().use { out -> out.writeAll(zip.source()) }
                written += entry.name to temp
            }
        }
        val order = pageOrder(written.map { it.first })
        val byName = written.toMap()
        order.forEachIndexed { index, name ->
            val extension = name.substringAfterLast('.').lowercase()
            fileSystem.atomicMove(byName.getValue(name), dir / "$index.$extension")
        }
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
            .filter { it.name != DONE && !it.name.startsWith("part-") }
            .sortedBy { it.name.substringBefore('.').toInt() }

    private companion object {
        const val DONE = ".done"
        const val DRAIN_BUFFER = 8192
        // The reader moves between neighbouring chapters; a few cover that
        // without a long read filling the phone's storage.
        const val KEPT = 5
    }
}
