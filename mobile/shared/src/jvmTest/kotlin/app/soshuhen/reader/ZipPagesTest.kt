package app.soshuhen.reader

import kotlinx.coroutines.test.runTest
import okio.FileSystem
import okio.Path
import okio.Path.Companion.toOkioPath
import okio.source
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ZipPagesTest {
    private val cache: Path = Files.createTempDirectory("zip-pages").toOkioPath()

    private fun zip(vararg entries: Pair<String, String>): ByteArray {
        val bytes = ByteArrayOutputStream()
        ZipOutputStream(bytes).use { out ->
            for ((name, body) in entries) {
                out.putNextEntry(ZipEntry(name))
                out.write(body.toByteArray())
                out.closeEntry()
            }
        }
        return bytes.toByteArray()
    }

    private fun source(bytes: ByteArray) = bytes.inputStream().source()

    private val sample = zip(
        "ComicInfo.xml" to "<x/>",
        "__MACOSX/._001.jpg" to "fork",
        "010.jpg" to "ten",
        "002.jpg" to "two",
    )

    @Test fun extractsInServerOrderSkippingNonPages() = runTest {
        val paths = ZipPages(cache).extract(7, source(sample))
        assertEquals(listOf("two", "ten"), paths.map { FileSystem.SYSTEM.read(it) { readUtf8() } })
        assertEquals(listOf("0.jpg", "1.jpg"), paths.map { it.name })
    }

    @Test fun secondOpenDoesNotReread() = runTest {
        val pages = ZipPages(cache)
        val first = pages.extract(7, source(sample))
        val second = pages.extract(7, source(ByteArray(0)))
        assertEquals(first, second)
    }

    @Test fun keepsOnlyFiveChapters() = runTest {
        val pages = ZipPages(cache)
        for (id in 1L..6L) pages.extract(id, source(sample))
        assertFalse(FileSystem.SYSTEM.exists(cache / "reader" / "1"))
        for (id in 2L..6L) assertTrue(FileSystem.SYSTEM.exists(cache / "reader" / id.toString()))
    }

    @Test fun reopeningAChapterKeepsItFresh() = runTest {
        val pages = ZipPages(cache)
        for (id in 1L..5L) pages.extract(id, source(sample))
        pages.extract(1, source(sample))
        pages.extract(6, source(sample))
        assertTrue(FileSystem.SYSTEM.exists(cache / "reader" / "1"))
        assertFalse(FileSystem.SYSTEM.exists(cache / "reader" / "2"))
    }

    @Test fun aHalfWrittenExtractionIsNotReused() = runTest {
        val pages = ZipPages(cache)
        // A zip cut short reads as a shorter zip, so the failure is a read that errors.
        val failing = object : java.io.InputStream() {
            var read = 0
            override fun read(): Int {
                if (read >= sample.size / 2) throw java.io.IOException("connection lost")
                return sample[read++].toInt() and 0xff
            }
        }.source()
        assertFailsWith<java.io.IOException> { pages.extract(9, failing) }
        val paths = pages.extract(9, source(sample))
        assertEquals(2, paths.size)
    }

    @Test fun pageCountCountsOnlyPages() = runTest {
        assertEquals(2, ZipPages(cache).pageCount(source(sample)))
    }

    @Test fun pageCountOfAnEmptyZipIsZero() = runTest {
        assertEquals(0, ZipPages(cache).pageCount(source(zip())))
    }

    @Test fun pageCountOfNonZipIsZero() = runTest {
        assertEquals(0, ZipPages(cache).pageCount(source("not a zip".toByteArray())))
    }
}
