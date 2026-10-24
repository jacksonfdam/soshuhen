package app.soshuhen.reader

import app.soshuhen.core.BookKind
import app.soshuhen.core.BookRef
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
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class EpubFilesTest {
    private val cache: Path = Files.createTempDirectory("epub-files").toOkioPath()
    private val volume = BookRef(BookKind.Volume, 41)

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

    private val container = "META-INF/container.xml" to
        """<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>"""
    private val opf = "OEBPS/content.opf" to
        """<package><manifest><item id="c" href="chapter.xhtml"/></manifest><spine><itemref idref="c"/></spine></package>"""
    private val chapter = "OEBPS/chapter.xhtml" to "<html><body><p>text</p></body></html>"
    private val whole = zip("mimetype" to "application/epub+zip", container, opf, chapter)

    private fun source(bytes: ByteArray) = bytes.inputStream().source()

    @Test fun unpacksOnceAndReusesTheSameVersion() = runTest {
        val files = EpubFiles(cache)
        val dir = files.unpack(volume, "v1", source(whole))
        assertEquals("<html><body><p>text</p></body></html>", FileSystem.SYSTEM.read(dir / "OEBPS/chapter.xhtml") { readUtf8() })
        assertEquals(dir, files.unpack(volume, "v1", source(ByteArray(0))))
        assertEquals("text", (readBook(FileSystem.SYSTEM, dir).sections.single().single() as Block.Paragraph).text.text)
    }

    @Test fun aNewVersionUnpacksAgain() = runTest {
        val files = EpubFiles(cache)
        files.unpack(volume, "v1", source(whole))
        val changed = zip(container, opf, "OEBPS/chapter.xhtml" to "<p>new</p>")
        val dir = files.unpack(volume, "v2", source(changed))
        assertEquals("<p>new</p>", FileSystem.SYSTEM.read(dir / "OEBPS/chapter.xhtml") { readUtf8() })
    }

    @Test fun aChapterAndAVolumeWithTheSameIdAreApart() = runTest {
        val files = EpubFiles(cache)
        val a = files.unpack(BookRef(BookKind.Chapter, 41), "v1", source(whole))
        val b = files.unpack(volume, "v1", source(whole))
        assertTrue(a != b)
    }

    @Test fun keepsOnlyThreeBooks() = runTest {
        val files = EpubFiles(cache)
        for (id in 1L..4L) files.unpack(BookRef(BookKind.Volume, id), "v1", source(whole))
        assertFalse(FileSystem.SYSTEM.exists(cache / "books" / "volume-1"))
        for (id in 2L..4L) assertTrue(FileSystem.SYSTEM.exists(cache / "books" / "volume-$id"))
    }

    @Test fun entriesEscapingTheRootAreSkipped() = runTest {
        val dir = EpubFiles(cache).unpack(volume, "v1", source(zip(container, opf, chapter, "../../evil.txt" to "x", "/abs.txt" to "y")))
        assertFalse(FileSystem.SYSTEM.exists(cache / "evil.txt"))
        assertFalse(FileSystem.SYSTEM.exists(dir / "abs.txt"))
        assertFalse(FileSystem.SYSTEM.exists(cache.parent!! / "evil.txt"))
    }

    @Test fun opensAWholeEpub() = runTest {
        assertTrue(EpubFiles(cache).opens(source(whole)))
    }

    @Test fun opensRejectsACutOffEpub() = runTest {
        assertFalse(EpubFiles(cache).opens(source(whole.copyOf(whole.size / 2))))
    }

    @Test fun opensRejectsAZipWithoutContainer() = runTest {
        assertFalse(EpubFiles(cache).opens(source(zip(opf, chapter))))
    }

    @Test fun opensRejectsASpineNamingAMissingFile() = runTest {
        assertFalse(EpubFiles(cache).opens(source(zip(container, opf))))
    }
}
