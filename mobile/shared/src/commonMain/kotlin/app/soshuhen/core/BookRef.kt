package app.soshuhen.core

/** What a copied file is: a chapter's archive, or a light novel volume's whole book. */
enum class BookKind(val key: String) { Chapter("chapter"), Volume("volume") }

/**
 * A chapter and a volume can share an id, since the server numbers them in
 * separate tables; everything kept per file is keyed by the pair.
 */
data class BookRef(val kind: BookKind, val id: Long)

/**
 * A volume's own title, or null when it only says "Volume 3" beside the
 * number already shown: imported volumes are titled that way.
 */
fun volumeTitle(number: Double, title: String?): String? {
    val shown = if (number % 1.0 == 0.0) number.toLong().toString() else number.toString()
    return title?.trim()?.takeUnless { it.isEmpty() || it.equals("Volume $shown", ignoreCase = true) }
}
