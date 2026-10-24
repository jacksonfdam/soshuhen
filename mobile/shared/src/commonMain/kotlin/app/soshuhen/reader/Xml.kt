package app.soshuhen.reader

sealed interface XmlEvent {
    data class Start(val name: String, val attributes: Map<String, String>, val selfClosing: Boolean) : XmlEvent
    data class End(val name: String) : XmlEvent
    data class Text(val text: String) : XmlEvent
}

/**
 * Just enough XML for an EPUB's container, package and chapters, written here
 * rather than pulled in: the app needs elements, attributes and text, and a
 * reader that keeps going through a publisher's malformed markup instead of
 * refusing the whole book. Names lose their namespace prefix and are lowercased,
 * so `dc:title` is `title` and `xlink:href` is `href`.
 */
class XmlReader(private val text: String) {
    fun events(): Sequence<XmlEvent> = sequence {
        var i = 0
        val pending = StringBuilder()
        suspend fun SequenceScope<XmlEvent>.flush() {
            if (pending.isNotEmpty()) {
                yield(XmlEvent.Text(decodeEntities(pending.toString())))
                pending.clear()
            }
        }
        while (i < text.length) {
            val c = text[i]
            if (c != '<') {
                val next = text.indexOf('<', i).let { if (it == -1) text.length else it }
                pending.append(text, i, next)
                i = next
                continue
            }
            when {
                text.startsWith("<!--", i) -> i = skipPast(i, "-->")
                text.startsWith("<![CDATA[", i) -> {
                    val end = text.indexOf("]]>", i).let { if (it == -1) text.length else it }
                    // Raw already: decoding it later would turn "&amp;" into "&".
                    flush()
                    yield(XmlEvent.Text(text.substring(i + 9, end)))
                    i = (end + 3).coerceAtMost(text.length)
                }
                text.startsWith("<!", i) || text.startsWith("<?", i) -> i = skipPast(i, ">")
                text.startsWith("</", i) && i + 2 < text.length && isNameStart(text[i + 2]) -> {
                    flush()
                    val end = text.indexOf('>', i).let { if (it == -1) text.length else it }
                    yield(XmlEvent.End(localName(text.substring(i + 2, end).trim())))
                    i = (end + 1).coerceAtMost(text.length)
                }
                i + 1 < text.length && isNameStart(text[i + 1]) -> {
                    flush()
                    val (start, after) = readStart(i)
                    yield(start)
                    i = after
                    // A script's or style's body is not markup; read as markup, a
                    // quoted "<p>" inside it would become text in the book.
                    if (!start.selfClosing && (start.name == "script" || start.name == "style")) {
                        val close = text.indexOf("</${start.name}", i, ignoreCase = true).let { if (it == -1) text.length else it }
                        val end = text.indexOf('>', close).let { if (it == -1) text.length else it }
                        yield(XmlEvent.End(start.name))
                        i = (end + 1).coerceAtMost(text.length)
                    }
                }
                else -> {
                    pending.append(c)
                    i++
                }
            }
        }
        flush()
    }

    private fun skipPast(from: Int, marker: String): Int =
        text.indexOf(marker, from).let { if (it == -1) text.length else it + marker.length }

    private fun readStart(from: Int): Pair<XmlEvent.Start, Int> {
        var i = from + 1
        val nameStart = i
        while (i < text.length && !text[i].isWhitespace() && text[i] != '>' && text[i] != '/') i++
        val name = localName(text.substring(nameStart, i))
        val attributes = linkedMapOf<String, String>()
        var selfClosing = false
        while (i < text.length) {
            val c = text[i]
            when {
                c == '>' -> return XmlEvent.Start(name, attributes, selfClosing) to i + 1
                c == '/' -> { selfClosing = true; i++ }
                c.isWhitespace() -> i++
                else -> {
                    selfClosing = false
                    val keyStart = i
                    while (i < text.length && text[i] != '=' && !text[i].isWhitespace() && text[i] != '>' && text[i] != '/') i++
                    val key = localName(text.substring(keyStart, i))
                    while (i < text.length && text[i].isWhitespace()) i++
                    var value = ""
                    if (i < text.length && text[i] == '=') {
                        i++
                        while (i < text.length && text[i].isWhitespace()) i++
                        if (i < text.length && (text[i] == '"' || text[i] == '\'')) {
                            val quote = text[i]
                            val end = text.indexOf(quote, i + 1).let { if (it == -1) text.length else it }
                            value = text.substring(i + 1, end)
                            i = (end + 1).coerceAtMost(text.length)
                        } else {
                            val valueStart = i
                            while (i < text.length && !text[i].isWhitespace() && text[i] != '>') i++
                            value = text.substring(valueStart, i)
                        }
                    }
                    attributes[key] = decodeEntities(value)
                }
            }
        }
        return XmlEvent.Start(name, attributes, selfClosing) to text.length
    }

    private fun isNameStart(c: Char) = c.isLetter() || c == '_'

    private fun localName(raw: String) = raw.substringAfter(':').lowercase()
}

// XML's five, and the HTML ones a book's prose actually uses. An EPUB's XHTML
// may only use the five, but files converted from HTML carry the rest.
private val NAMED = mapOf(
    "amp" to "&", "lt" to "<", "gt" to ">", "quot" to "\"", "apos" to "'",
    "nbsp" to " ", "mdash" to "—", "ndash" to "–", "hellip" to "…",
    "lsquo" to "‘", "rsquo" to "’", "ldquo" to "“", "rdquo" to "”",
    "laquo" to "«", "raquo" to "»", "middot" to "·", "copy" to "©", "shy" to "­",
)

fun decodeEntities(raw: String): String {
    if ('&' !in raw) return raw
    val out = StringBuilder(raw.length)
    var i = 0
    while (i < raw.length) {
        val c = raw[i]
        val end = if (c == '&') raw.indexOf(';', i).takeIf { it in (i + 2)..(i + 10) } else null
        if (end == null) {
            out.append(c)
            i++
            continue
        }
        val name = raw.substring(i + 1, end)
        val decoded = when {
            name.startsWith("#x") || name.startsWith("#X") -> name.drop(2).toIntOrNull(16)?.let(::codePoint)
            name.startsWith("#") -> name.drop(1).toIntOrNull()?.let(::codePoint)
            else -> NAMED[name]
        }
        if (decoded == null) {
            out.append(c)
            i++
        } else {
            out.append(decoded)
            i = end + 1
        }
    }
    return out.toString()
}

private fun codePoint(value: Int): String? = when {
    value in 0..0xFFFF -> value.toChar().toString()
    value in 0x10000..0x10FFFF -> {
        val v = value - 0x10000
        charArrayOf((0xD800 + (v shr 10)).toChar(), (0xDC00 + (v and 0x3FF)).toChar()).concatToString()
    }
    else -> null
}
