package app.soshuhen.reader

import okio.Path.Companion.toPath
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PaginatorTest {
    private var measured = 0

    // Ten characters to a 10 px line; an image is one 30 px line.
    private val measure = BlockMeasure { block, _ ->
        measured++
        when (block) {
            is Block.Image -> listOf(Line(0, 0, 30))
            Block.Break -> listOf(Line(0, 0, 10))
            is Block.Heading, is Block.Paragraph -> {
                val n = block.length()
                (0 until n step 10).map { Line(it, minOf(it + 10, n), 10) }
            }
        }
    }

    private fun p(chars: Int) = Block.Paragraph(Styled("x".repeat(chars)))

    private fun paginator(book: Book, height: Int = 50, gap: Int = 0) = Paginator(book, measure, width = 100, height = height, gap = gap)

    private val start = ProsePosition(0, 0, 0)

    @Test fun aPageHoldsAsManyLinesAsFit() {
        val book = Book(null, listOf(listOf(p(20), p(20), p(20))))
        val page = paginator(book).pageFrom(start)
        assertEquals(start, page.start)
        assertEquals(ProsePosition(0, 2, 10), page.end)
    }

    @Test fun aParagraphSplitsAcrossPages() {
        val book = Book(null, listOf(listOf(p(80))))
        val pages = paginator(book)
        val first = pages.pageFrom(start)
        assertEquals(ProsePosition(0, 0, 50), first.end)
        val second = pages.pageFrom(first.end)
        assertEquals(ProsePosition(0, 0, 50), second.start)
        assertTrue(pages.isLast(second))
    }

    @Test fun theGapBetweenBlocksTakesRoom() {
        val book = Book(null, listOf(listOf(p(20), p(20), p(20))))
        // 20 + 5 + 20 = 45 fits; the next block's gap and line do not.
        assertEquals(ProsePosition(0, 2, 0), paginator(book, gap = 5).pageFrom(start).end)
    }

    @Test fun aSectionStartsANewPage() {
        val book = Book(null, listOf(listOf(p(10)), listOf(p(10))))
        val pages = paginator(book)
        val first = pages.pageFrom(start)
        assertEquals(ProsePosition(1, 0, 0), first.end)
        val last = pages.pageFrom(first.end)
        assertEquals(ProsePosition(2, 0, 0), last.end)
        assertTrue(pages.isLast(last))
    }

    @Test fun aPositionInsideALineSnapsToItsStart() {
        val book = Book(null, listOf(listOf(p(80))))
        assertEquals(ProsePosition(0, 0, 30), paginator(book).pageFrom(ProsePosition(0, 0, 37)).start)
    }

    @Test fun anImageTallerThanThePageStillGetsAPage() {
        val book = Book(null, listOf(listOf(Block.Image("/i.jpg".toPath()), p(10))))
        val page = paginator(book, height = 20).pageFrom(start)
        assertEquals(ProsePosition(0, 1, 0), page.end)
    }

    @Test fun pageBeforeEndsWhereTheNextBegins() {
        val book = Book(null, listOf(listOf(p(20), p(40), p(30))))
        val pages = paginator(book)
        val first = pages.pageFrom(start)
        val second = pages.pageFrom(first.end)
        assertEquals(first, pages.pageBefore(second.start))
        assertNull(pages.pageBefore(start))
    }

    @Test fun pageBeforeCrossesIntoTheEndOfThePreviousSection() {
        val book = Book(null, listOf(listOf(p(80)), listOf(p(10))))
        val back = paginator(book).pageBefore(ProsePosition(1, 0, 0))!!
        assertEquals(ProsePosition(0, 0, 30), back.start)
        assertEquals(ProsePosition(1, 0, 0), back.end)
    }

    // Inside the first line of a section is that section's start.
    @Test fun pageBeforeAPositionInsideASectionsFirstLine() {
        val book = Book(null, listOf(listOf(p(10)), listOf(p(30))))
        assertEquals(Page(start, ProsePosition(1, 0, 0)), paginator(book).pageBefore(ProsePosition(1, 0, 5)))
        assertNull(paginator(book).pageBefore(ProsePosition(0, 0, 5)))
    }

    // The whole point of positions over page numbers.
    @Test fun resizingKeepsTheFirstCharacterVisible() {
        val book = Book(null, listOf(List(30) { p(35) }))
        val reading = paginator(book, height = 100).pageFrom(ProsePosition(0, 12, 20))
        val smaller = paginator(book, height = 60).pageFrom(reading.start)
        assertTrue(book.charsBefore(smaller.start) <= book.charsBefore(reading.start))
        assertTrue(book.charsBefore(reading.start) < book.charsBefore(smaller.end))
    }

    @Test fun onlyBlocksNearThePositionAreMeasured() {
        val book = Book(null, listOf(List(3000) { p(30) }))
        val pages = paginator(book)
        val page = pages.pageFrom(ProsePosition(0, 2500, 0))
        pages.pageBefore(page.start)
        assertTrue(measured < 50, "measured $measured blocks")
    }
}
