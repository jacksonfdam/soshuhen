package app.soshuhen.reader

// Mirrors backend/app/reader/archive.py and frontend/.../reader/lib/spreads.ts.
// The app's page n has to be the server's page n: reading progress is stored
// as an index and travels between the two.

private val imageSuffixes = listOf(".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")

fun isPage(name: String): Boolean {
    // An archive zipped on a Mac carries __MACOSX/._001.jpg beside every page:
    // resource forks with an image's name and no image inside. Counted, they
    // shift every page after them by one.
    if (name.endsWith("/") || name.startsWith("__MACOSX/")) return false
    if (name.substringAfterLast('/').startsWith(".")) return false
    val lower = name.lowercase()
    return imageSuffixes.any { lower.endsWith(it) }
}

/**
 * A run of digits compared as a number without being parsed into one: a name
 * with more digits than a Long holds must still sort, not throw.
 */
private class DigitRun(digits: String) : Comparable<DigitRun> {
    private val significant = digits.trimStart('0')

    override fun compareTo(other: DigitRun): Int =
        if (significant.length != other.significant.length) {
            significant.length.compareTo(other.significant.length)
        } else {
            significant.compareTo(other.significant)
        }
}

fun naturalKey(name: String): List<Comparable<*>> {
    // Archives Komga adopted were written by other tools, and plain sorting
    // puts "Page 10" before "Page 2". Text and digit parts alternate, text
    // first, so two keys always compare like with like.
    val parts = mutableListOf<Comparable<*>>()
    var index = 0
    while (index <= name.length) {
        var end = index
        while (end < name.length && name[end] !in '0'..'9') end++
        parts += name.substring(index, end).lowercase()
        if (end >= name.length) break
        var digitsEnd = end
        while (digitsEnd < name.length && name[digitsEnd] in '0'..'9') digitsEnd++
        parts += DigitRun(name.substring(end, digitsEnd))
        index = digitsEnd
        if (index == name.length) {
            parts += ""
            break
        }
    }
    return parts
}

@Suppress("UNCHECKED_CAST")
private val naturalOrder = Comparator<List<Comparable<*>>> { a, b ->
    for (i in 0 until minOf(a.size, b.size)) {
        val result = (a[i] as Comparable<Any>).compareTo(b[i])
        if (result != 0) return@Comparator result
    }
    a.size.compareTo(b.size)
}

// sortedWith is stable, like Python's sorted, so names that tie ("01" and "1")
// keep their archive order on both sides.
fun pageOrder(names: List<String>): List<String> =
    names.filter(::isPage).sortedWith { a, b -> naturalOrder.compare(naturalKey(a), naturalKey(b)) }

fun spreads(pageCount: Int, mode: String): List<List<Int>> {
    if (mode != "double") return List(pageCount) { listOf(it) }
    // The first page stands alone, the way a printed volume opens on its
    // cover; pairing it shifts every later spread by one and splits two-page
    // art down the middle.
    val groups = mutableListOf<List<Int>>()
    if (pageCount > 0) groups += listOf(0)
    var index = 1
    while (index < pageCount) {
        groups += if (index + 1 < pageCount) listOf(index, index + 1) else listOf(index)
        index += 2
    }
    return groups
}

fun spreadOf(groups: List<List<Int>>, page: Int): Int {
    val found = groups.indexOfFirst { page in it }
    return if (found == -1) 0 else found
}
