package app.soshuhen.core

/** What a copied file is: a chapter's archive, or a light novel volume's whole book. */
enum class BookKind(val key: String) { Chapter("chapter"), Volume("volume") }

/**
 * A chapter and a volume can share an id, since the server numbers them in
 * separate tables; everything kept per file is keyed by the pair.
 */
data class BookRef(val kind: BookKind, val id: Long)
