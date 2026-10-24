package app.soshuhen.reader

/** One laid-out line of a block: characters [start, end) of its text, [height] pixels tall. */
data class Line(val start: Int, val end: Int, val height: Int)

/**
 * How tall a block's lines are at a width. Compose measures in the app; a test
 * measures by arithmetic, which is what keeps the paging rules testable.
 */
fun interface BlockMeasure {
    fun lines(block: Block, width: Int): List<Line>
}

/**
 * A screenful of the book: [start] inclusive, [end] exclusive. The last page of
 * a section ends at the next section's start, and the book's last page at
 * `ProsePosition(sections.size, 0, 0)`.
 */
data class Page(val start: ProsePosition, val end: ProsePosition)

/**
 * Pages built outward from wherever the reader is, never for a whole book up
 * front: one volume is a single 2,700-paragraph section, and measuring all of
 * it before the first page shows would be a wait on every open and every
 * change of type size. Each section starts a page, as a book's chapters do.
 */
class Paginator(
    private val book: Book,
    private val measure: BlockMeasure,
    private val width: Int,
    private val height: Int,
    private val gap: Int,
) {
    private val measured = mutableMapOf<Long, List<Line>>()

    private fun lines(section: Int, block: Int): List<Line> =
        measured.getOrPut(section.toLong() shl 32 or block.toLong()) {
            measure.lines(book.sections[section][block], width).ifEmpty { listOf(Line(0, 0, 0)) }
        }

    private fun lineIndex(p: ProsePosition): Int = lines(p.section, p.block).indexOfLast { it.start <= p.offset }.coerceAtLeast(0)

    fun pageFrom(p: ProsePosition): Page {
        val at = book.clamp(p)
        val s = at.section
        val section = book.sections[s]
        var b = at.block
        var l = lineIndex(at)
        val start = ProsePosition(s, b, lines(s, b)[l].start)
        var used = 0
        var first = true
        while (b < section.size) {
            val blockLines = lines(s, b)
            while (l < blockLines.size) {
                val needed = blockLines[l].height + if (!first && l == 0) gap else 0
                // A line taller than the page still gets one, or it could never be read.
                if (!first && used + needed > height) return Page(start, ProsePosition(s, b, blockLines[l].start))
                used += needed
                first = false
                l++
            }
            b++
            l = 0
        }
        return Page(start, ProsePosition(s + 1, 0, 0))
    }

    /** The page that ends exactly at [p], laid out backwards from it; null at the book's start. */
    fun pageBefore(p: ProsePosition): Page? {
        // Snapped first: a place inside a section's first line is that section's start.
        val snapped = if (p.section >= book.sections.size) null else book.clamp(p).let {
            ProsePosition(it.section, it.block, lines(it.section, it.block)[lineIndex(it)].start)
        }
        var s: Int
        var b: Int
        var l: Int
        val end: ProsePosition
        if (snapped == null || (snapped.block == 0 && snapped.offset == 0)) {
            // Ending at a section's start means ending at the previous section's end.
            s = (snapped?.section ?: book.sections.size) - 1
            if (s < 0) return null
            b = book.sections[s].lastIndex
            l = lines(s, b).lastIndex
            end = ProsePosition(s + 1, 0, 0)
        } else {
            s = snapped.section
            b = snapped.block
            l = lineIndex(snapped) - 1
            if (l < 0) {
                b--
                l = lines(s, b).lastIndex
            }
            end = snapped
        }
        var used = 0
        var startBlock = b
        var startLine = l
        var first = true
        while (b >= 0) {
            val blockLines = lines(s, b)
            while (l >= 0) {
                // The gap sits above a block's first line, so walking up it is
                // paid when the line below belongs to the next block.
                val below = if (!first && l == blockLines.lastIndex) gap else 0
                val needed = blockLines[l].height + below
                if (!first && used + needed > height) {
                    return Page(ProsePosition(s, startBlock, lines(s, startBlock)[startLine].start), end)
                }
                used += needed
                first = false
                startBlock = b
                startLine = l
                l--
            }
            b--
            if (b >= 0) l = lines(s, b).lastIndex
        }
        return Page(ProsePosition(s, startBlock, lines(s, startBlock)[startLine].start), end)
    }

    fun isLast(page: Page): Boolean = page.end.section >= book.sections.size
}
