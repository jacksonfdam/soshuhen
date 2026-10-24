package app.soshuhen.reader

import app.soshuhen.core.BookExtractor
import app.soshuhen.core.BookRef
import app.soshuhen.core.EpubCheck
import app.soshuhen.core.NoRoomForPages
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okio.FileSystem
import okio.Path
import okio.Path.Companion.toPath
import okio.Source
import okio.buffer
import java.io.ByteArrayOutputStream
import java.util.zip.ZipInputStream

/**
 * EPUBs unpacked once into the app's own cache, as ZipPages does for a CBZ's
 * pages: the reader reads the book's files many times, and the zip once. The
 * cache is never the user's folder.
 */
class EpubFiles(
    cacheDir: Path,
    private val fileSystem: FileSystem = FileSystem.SYSTEM,
) : EpubCheck, BookExtractor {
    private val root = cacheDir / "books"
    private val lock = Mutex()

    override suspend fun unpack(ref: BookRef, version: String, source: Source): Path = lock.withLock {
        withContext(Dispatchers.IO) {
            val dir = root / "${ref.kind.key}-${ref.id}"
            val done = dir / DONE
            val from = dir / FROM
            // A directory with no marker is an unpacking that died halfway, and one
            // from another copy of the book would open the old copy's text.
            val current = fileSystem.exists(done) && fileSystem.exists(from) &&
                fileSystem.read(from) { readUtf8() } == version
            if (!current) {
                fileSystem.deleteRecursively(dir)
                write(dir, source)
                cache { fileSystem.write(from) { writeUtf8(version) } }
            }
            cache { mark(dir) }
            prune(keep = dir)
            dir
        }
    }

    override suspend fun opens(source: Source): Boolean = withContext(Dispatchers.IO) {
        val names = mutableSetOf<String>()
        val small = mutableMapOf<String, String>()
        val scratch = ByteArray(DRAIN_BUFFER)
        ZipInputStream(source.buffer().inputStream()).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                names += entry.name
                // Draining every entry is what notices a cut-off archive: a header
                // alone reads fine, only the data after it runs out.
                val keep = entry.name == CONTAINER || entry.name.endsWith(".opf", ignoreCase = true)
                val kept = if (keep) ByteArrayOutputStream() else null
                while (true) {
                    val n = zip.read(scratch)
                    if (n == -1) break
                    kept?.write(scratch, 0, n)
                }
                kept?.let { small[entry.name] = it.toString(Charsets.UTF_8) }
            }
        }
        val opfName = small[CONTAINER]?.let { container ->
            XmlReader(container).events().filterIsInstance<XmlEvent.Start>()
                .firstOrNull { it.name == "rootfile" }?.attributes?.get("full-path")
        } ?: return@withContext false
        val opf = small[opfName] ?: return@withContext false
        val base = "/".toPath() / opfName
        val manifest = mutableMapOf<String, String>()
        val spine = mutableListOf<String>()
        XmlReader(opf).events().filterIsInstance<XmlEvent.Start>().forEach {
            when (it.name) {
                "item" -> {
                    val id = it.attributes["id"]
                    val href = it.attributes["href"]
                    if (id != null && href != null) manifest[id] = href
                }
                "itemref" -> it.attributes["idref"]?.let(spine::add)
            }
        }
        spine.any { id ->
            val path = manifest[id]?.let { href -> inside("/".toPath(), base.parent!!, href) }
            path != null && path.toString().removePrefix("/") in names
        }
    }

    private fun write(dir: Path, source: Source) {
        cache { fileSystem.createDirectories(dir) }
        ZipInputStream(source.buffer().inputStream()).use { zip ->
            val chunk = ByteArray(DRAIN_BUFFER)
            while (true) {
                val entry = zip.nextEntry ?: break
                // A name that climbs out of the book or starts at the root would
                // write wherever it pointed; a book has no business there.
                val name = entry.name.replace('\\', '/')
                if (name.startsWith("/") || name.split('/').any { it == ".." }) continue
                val target = dir / name
                if (entry.isDirectory) {
                    cache { fileSystem.createDirectories(target) }
                    continue
                }
                target.parent?.let { cache { fileSystem.createDirectories(it) } }
                cache { fileSystem.sink(target).buffer() }.use { out ->
                    // Read and write apart, so a failing read blames the book
                    // and a failing write blames the cache.
                    while (true) {
                        val n = zip.read(chunk)
                        if (n == -1) break
                        cache { out.write(chunk, 0, n) }
                    }
                    cache { out.flush() }
                }
            }
        }
    }

    private inline fun <T> cache(block: () -> T): T = try {
        block()
    } catch (e: java.io.IOException) {
        throw NoRoomForPages(e)
    }

    private fun mark(dir: Path) {
        val newest = books().maxOfOrNull { sequence(it) } ?: 0L
        fileSystem.write(dir / DONE) { writeUtf8((newest + 1).toString()) }
    }

    private fun prune(keep: Path) {
        val recent = books().sortedByDescending { sequence(it) }
        for (stale in recent.drop(KEPT)) if (stale != keep) fileSystem.deleteRecursively(stale)
    }

    private fun books(): List<Path> =
        if (fileSystem.exists(root)) fileSystem.list(root).filter { fileSystem.exists(it / DONE) } else emptyList()

    private fun sequence(dir: Path): Long = fileSystem.read(dir / DONE) { readUtf8() }.toLongOrNull() ?: 0L

    private companion object {
        const val CONTAINER = "META-INF/container.xml"
        const val DONE = ".done"
        const val FROM = ".from"
        const val DRAIN_BUFFER = 8192
        // A book is a whole volume, not a chapter: a few cover the one being read
        // and the ones beside it without filling the phone.
        const val KEPT = 3
    }
}
