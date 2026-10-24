package app.soshuhen.reader

import kotlinx.serialization.Serializable

/**
 * A place in a book as the character it is at, not the page it fell on: a page
 * number means something else the moment the type size or the screen changes.
 */
@Serializable
data class ProsePosition(val section: Int, val block: Int, val offset: Int)

/** An image or a scene break counts as one character, so the slider can stop on it. */
fun Block.length(): Int = when (this) {
    is Block.Heading -> text.text.length.coerceAtLeast(1)
    is Block.Paragraph -> text.text.length.coerceAtLeast(1)
    is Block.Image, Block.Break -> 1
}

fun Book.length(): Int = sections.sumOf { section -> section.sumOf { it.length() } }

fun Book.charsBefore(p: ProsePosition): Int {
    val at = clamp(p)
    var count = 0
    for (s in 0 until at.section) count += sections[s].sumOf { it.length() }
    val section = sections[at.section]
    for (b in 0 until at.block) count += section[b].length()
    return count + at.offset
}

fun Book.positionAtChar(n: Int): ProsePosition {
    var left = n.coerceIn(0, (length() - 1).coerceAtLeast(0))
    for ((s, section) in sections.withIndex()) {
        for ((b, block) in section.withIndex()) {
            val size = block.length()
            if (left < size) return ProsePosition(s, b, left)
            left -= size
        }
    }
    return clamp(ProsePosition(sections.lastIndex, Int.MAX_VALUE, Int.MAX_VALUE))
}

/** The nearest real character to [p], for a position saved against another copy of the book. */
fun Book.clamp(p: ProsePosition): ProsePosition {
    val s = p.section.coerceIn(0, sections.lastIndex)
    val section = sections[s]
    val b = p.block.coerceIn(0, section.lastIndex)
    return ProsePosition(s, b, p.offset.coerceIn(0, section[b].length() - 1))
}
