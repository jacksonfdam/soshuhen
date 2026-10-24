package app.soshuhen.reader

import okio.FileSystem
import okio.Path

enum class Emphasis { Bold, Italic }

/** [start] inclusive, [end] exclusive, in the paragraph's own text. */
data class Span(val start: Int, val end: Int, val emphasis: Emphasis)

data class Styled(val text: String, val spans: List<Span> = emptyList())

/**
 * What the reader draws. A book's own styling is not kept: the reader sets
 * every novel in the user's type, and only the structure that carries meaning
 * (headings, emphasis, line breaks, pictures, scene breaks) survives.
 */
sealed interface Block {
    data class Heading(val level: Int, val text: Styled) : Block
    data class Paragraph(val text: Styled) : Block
    /** [path] is a file inside the unpacked book: never a URL. */
    data class Image(val path: Path) : Block
    data object Break : Block
}

/** [sections] follow the spine; a section is one of the book's own files. */
data class Book(val title: String?, val sections: List<List<Block>>)

class NotAnEpub(message: String) : Exception(message)

/** Reads a book already unpacked at [root]. */
fun readBook(fs: FileSystem, root: Path): Book {
    val container = root / "META-INF" / "container.xml"
    if (!fs.exists(container)) throw NotAnEpub("no META-INF/container.xml")
    val opfHref = XmlReader(fs.read(container) { readUtf8() }).events()
        .filterIsInstance<XmlEvent.Start>()
        .firstOrNull { it.name == "rootfile" }?.attributes?.get("full-path")
        ?: throw NotAnEpub("container names no package")
    val opf = inside(root, root, opfHref)?.takeIf { fs.exists(it) } ?: throw NotAnEpub("package $opfHref is missing")
    val opfDir = opf.parent ?: root

    val manifest = mutableMapOf<String, String>()
    val spine = mutableListOf<String>()
    var title: String? = null
    var inTitle = false
    for (event in XmlReader(fs.read(opf) { readUtf8() }).events()) {
        when (event) {
            is XmlEvent.Start -> when (event.name) {
                "item" -> {
                    val id = event.attributes["id"]
                    val href = event.attributes["href"]
                    if (id != null && href != null) manifest[id] = href
                }
                "itemref" -> event.attributes["idref"]?.let(spine::add)
                "title" -> inTitle = title == null
            }
            is XmlEvent.End -> if (event.name == "title") inTitle = false
            is XmlEvent.Text -> if (inTitle) title = (title.orEmpty() + event.text).trim().ifEmpty { null }
        }
    }

    val sections = spine.mapNotNull { id ->
        val file = manifest[id]?.let { inside(root, opfDir, it) }?.takeIf { fs.exists(it) } ?: return@mapNotNull null
        blocksOf(fs, root, file).takeIf { it.isNotEmpty() }
    }
    if (sections.isEmpty()) throw NotAnEpub("the spine names no readable file")
    return Book(title, sections)
}

private val BLOCK_ELEMENTS = setOf(
    "p", "div", "li", "ul", "ol", "dl", "dd", "dt", "blockquote", "section", "article", "body",
    "header", "footer", "aside", "nav", "figure", "figcaption", "table", "tr", "td", "th", "pre", "main",
)
private val HEADINGS = mapOf("h1" to 1, "h2" to 2, "h3" to 3, "h4" to 4, "h5" to 5, "h6" to 6)
private val SKIPPED = setOf("head", "script", "style", "title")

private fun blocksOf(fs: FileSystem, root: Path, file: Path): List<Block> {
    val dir = file.parent ?: root
    val blocks = mutableListOf<Block>()
    val text = StringBuilder()
    val spans = mutableListOf<Span>()
    val open = mutableListOf<Pair<String, Int>>()
    var heading: Int? = null
    var skipping = 0

    fun flush() {
        while (text.isNotEmpty() && text.last() == ' ') text.setLength(text.length - 1)
        if (text.isNotEmpty()) {
            val length = text.length
            val styled = Styled(
                text.toString(),
                spans.mapNotNull { s -> s.copy(end = minOf(s.end, length)).takeIf { it.start < it.end } }.sortedBy { it.start },
            )
            blocks += heading?.let { Block.Heading(it, styled) } ?: Block.Paragraph(styled)
        }
        text.clear()
        spans.clear()
        // Still-open emphasis carries into the next block from its first character.
        for (index in open.indices) open[index] = open[index].first to 0
    }

    fun append(raw: String) {
        for (c in raw) {
            if (c.isWhitespace() && c != ' ') {
                if (text.isNotEmpty() && text.last() != ' ' && text.last() != '\n') text.append(' ')
            } else {
                text.append(c)
            }
        }
    }

    fun image(href: String?) {
        val path = href?.let { inside(root, dir, it) }?.takeIf { fs.exists(it) } ?: return
        flush()
        blocks += Block.Image(path)
    }

    for (event in XmlReader(fs.read(file) { readUtf8() }).events()) {
        when (event) {
            is XmlEvent.Start -> {
                if (event.name in SKIPPED && !event.selfClosing) skipping++
                if (skipping > 0) continue
                when (val name = event.name) {
                    in HEADINGS -> { flush(); heading = HEADINGS.getValue(name) }
                    in BLOCK_ELEMENTS -> flush()
                    "br" -> {
                        while (text.isNotEmpty() && text.last() == ' ') text.setLength(text.length - 1)
                        if (text.isNotEmpty()) text.append('\n')
                    }
                    "hr" -> { flush(); blocks += Block.Break }
                    "img" -> image(event.attributes["src"])
                    "image" -> image(event.attributes["href"])
                    "b", "strong" -> if (!event.selfClosing) open += "bold" to text.length
                    "i", "em", "cite" -> if (!event.selfClosing) open += "italic" to text.length
                }
            }
            is XmlEvent.End -> {
                if (event.name in SKIPPED) {
                    skipping = (skipping - 1).coerceAtLeast(0)
                    continue
                }
                if (skipping > 0) continue
                when (val name = event.name) {
                    in HEADINGS -> { flush(); heading = null }
                    in BLOCK_ELEMENTS -> flush()
                    "b", "strong", "i", "em", "cite" -> {
                        val kind = if (name == "b" || name == "strong") "bold" else "italic"
                        val index = open.indexOfLast { it.first == kind }
                        if (index >= 0) {
                            val start = open.removeAt(index).second
                            val emphasis = if (kind == "bold") Emphasis.Bold else Emphasis.Italic
                            if (start < text.length) spans += Span(start, text.length, emphasis)
                        }
                    }
                }
            }
            is XmlEvent.Text -> if (skipping == 0) append(event.text)
        }
    }
    flush()
    return blocks
}

private val SCHEME = Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:")

/**
 * A reference resolved against [base], or null when it names anything that is
 * not a file of this book: a URL of any scheme, a protocol-relative one, or a
 * path that climbs out of [root]. This is the line that keeps a book from
 * making the phone reach anywhere.
 */
internal fun inside(root: Path, base: Path, href: String): Path? {
    val clean = href.substringBefore('#').substringBefore('?').trim()
    if (clean.isEmpty() || clean.startsWith("//") || SCHEME.containsMatchIn(clean)) return null
    val resolved = (if (clean.startsWith("/")) root / percentDecode(clean.trimStart('/')) else base / percentDecode(clean)).normalized()
    val rootText = root.normalized().toString().trimEnd('/')
    return resolved.takeIf { it.toString().startsWith("$rootText/") }
}

private fun percentDecode(raw: String): String {
    if ('%' !in raw) return raw
    val bytes = mutableListOf<Byte>()
    var i = 0
    while (i < raw.length) {
        val hex = if (raw[i] == '%' && i + 2 < raw.length) raw.substring(i + 1, i + 3).toIntOrNull(16) else null
        if (hex != null) {
            bytes += hex.toByte()
            i += 3
        } else {
            bytes += raw[i].toString().encodeToByteArray().toList()
            i++
        }
    }
    return bytes.toByteArray().decodeToString()
}
