package app.soshuhen.reader

import okio.Path
import okio.Path.Companion.toPath
import okio.fakefilesystem.FakeFileSystem
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class EpubTest {
    private val fs = FakeFileSystem()
    private val root = "/book".toPath()

    private fun write(name: String, text: String) {
        val path = root / name
        path.parent?.let { fs.createDirectories(it) }
        fs.write(path) { writeUtf8(text) }
    }

    private fun xhtml(body: String) =
        """<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title>
        <link rel="stylesheet" href="https://cdn.example.com/x.css"/><style>p { color: red }</style></head>
        <body>$body</body></html>"""

    private fun book(vararg chapters: Pair<String, String>, title: String = "Moonlit") {
        write(
            "META-INF/container.xml",
            """<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
            <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""",
        )
        val items = chapters.mapIndexed { i, (name, _) -> """<item id="c$i" href="$name" media-type="application/xhtml+xml"/>""" }
        val refs = chapters.indices.map { """<itemref idref="c$it"/>""" }
        write(
            "OEBPS/content.opf",
            """<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">
            <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>$title</dc:title></metadata>
            <manifest>${items.joinToString("")}<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"/></manifest>
            <spine>${refs.joinToString("")}</spine></package>""",
        )
        chapters.forEach { (name, body) -> write("OEBPS/$name", xhtml(body)) }
    }

    private fun read() = readBook(fs, root)

    private fun texts(blocks: List<Block>) = blocks.map {
        when (it) {
            is Block.Heading -> "h${it.level}:${it.text.text}"
            is Block.Paragraph -> it.text.text
            is Block.Image -> "img:${it.path.name}"
            Block.Break -> "---"
        }
    }

    @Test fun readsTheSpineInOrder() {
        book("b.xhtml" to "<p>first</p>", "a.xhtml" to "<p>second</p>")
        val book = read()
        assertEquals("Moonlit", book.title)
        assertEquals(listOf(listOf("first"), listOf("second")), book.sections.map(::texts))
    }

    @Test fun keepsBoldAndItalicAsSpans() {
        book("c.xhtml" to "<p>a <i>b</i> <b>c</b> <em>d</em><strong>e</strong></p>")
        val p = read().sections.single().single() as Block.Paragraph
        assertEquals("a b c de", p.text.text)
        assertEquals(
            listOf(
                Span(2, 3, Emphasis.Italic), Span(4, 5, Emphasis.Bold),
                Span(6, 7, Emphasis.Italic), Span(7, 8, Emphasis.Bold),
            ),
            p.text.spans,
        )
    }

    @Test fun collapsesWhitespaceAndKeepsBr() {
        book("c.xhtml" to "<p>  one\n   two <br/>three  </p><p>   </p>")
        assertEquals(listOf("one two\nthree"), texts(read().sections.single()))
    }

    @Test fun headingsBreaksAndSectionsBecomeBlocks() {
        book("c.xhtml" to "<section><h2>Chapter 1</h2><div><p>x</p></div><hr/><div>loose text</div></section>")
        assertEquals(listOf("h2:Chapter 1", "x", "---", "loose text"), texts(read().sections.single()))
    }

    @Test fun resolvesImagesRelativeToTheXhtml() {
        book("text/c.xhtml" to """<p>a</p><img src="../images/1.jpg" alt=""/><svg><image xlink:href="../images/2.png"/></svg>""")
        write("OEBPS/images/1.jpg", "jpg")
        write("OEBPS/images/2.png", "png")
        val blocks = read().sections.single()
        assertEquals(listOf("a", "img:1.jpg", "img:2.png"), texts(blocks))
        assertEquals(root / "OEBPS/images/1.jpg", (blocks[1] as Block.Image).path)
    }

    // Nothing in a book may make the phone reach outside the home server.
    @Test fun dropsRemoteAndEscapingImages() {
        book(
            "c.xhtml" to """<p>a</p><img src="https://x.example/y.jpg"/><img src="//x.example/z.jpg"/>
            <img src="data:image/png;base64,AAAA"/><img src="../../../etc/passwd"/><img src="missing.jpg"/>""",
        )
        assertEquals(listOf("a"), texts(read().sections.single()))
    }

    @Test fun decodesEntities() {
        book("c.xhtml" to "<p>&amp; &lt;&gt; &quot;x&quot; &#8212; &#x2026; &hellip;&nbsp;&mdash;&rsquo;</p>")
        assertEquals("& <> \"x\" — … … —’", texts(read().sections.single()).single())
    }

    @Test fun skipsScriptsAndComments() {
        book("c.xhtml" to "<p>a<!-- hidden --></p><script>var x = '<p>no</p>';</script><p><![CDATA[b]]></p>")
        assertEquals(listOf("a", "b"), texts(read().sections.single()))
    }

    @Test fun aMissingSpineFileIsSkipped() {
        book("c.xhtml" to "<p>a</p>", "gone.xhtml" to "<p>b</p>")
        fs.delete(root / "OEBPS/gone.xhtml")
        assertEquals(1, read().sections.size)
    }

    @Test fun aMissingContainerIsNotAnEpub() {
        fs.createDirectories(root)
        assertFailsWith<NotAnEpub> { read() }
    }

    @Test fun aBookWithNoReadableSpineIsNotAnEpub() {
        book("c.xhtml" to "<p>a</p>")
        fs.delete(root / "OEBPS/c.xhtml")
        assertFailsWith<NotAnEpub> { read() }
    }

    @Test fun aLongSingleSectionParses() {
        book("c.xhtml" to (1..3000).joinToString("") { "<p>Paragraph $it of the volume.</p>" })
        assertEquals(3000, read().sections.single().size)
    }

    @Test fun positionsRoundTripThroughCharacterCounts() {
        book("a.xhtml" to "<p>abcd</p><hr/><p>ef</p>", "b.xhtml" to "<p>ghi</p>")
        val book = read()
        assertEquals(4 + 1 + 2 + 3, book.length())
        val p = ProsePosition(1, 0, 2)
        assertEquals(9, book.charsBefore(p))
        assertEquals(p, book.positionAtChar(9))
        assertEquals(ProsePosition(0, 1, 0), book.positionAtChar(4))
        assertEquals(ProsePosition(0, 0, 0), book.positionAtChar(-5))
        assertEquals(ProsePosition(1, 0, 2), book.positionAtChar(99))
        assertEquals(ProsePosition(0, 2, 1), book.clamp(ProsePosition(0, 2, 40)))
        assertTrue(book.clamp(ProsePosition(7, 0, 0)).section == 1)
    }

    // A trailing break is an empty last line: measured, it ends a page past the text.
    @Test fun trailingBreaksAreDropped() {
        book("c.xhtml" to "<p>text<br/></p><p>a<br/><br/> </p>")
        assertEquals(listOf("text", "a"), texts(read().sections.single()))
    }
}
