package app.soshuhen.core

import okio.Source

/**
 * Whether a copied EPUB can be read, before it takes its place on the device.
 * It has no pages to count, so ArchiveCheck's question does not fit; a book
 * whose package names no text it holds is as broken as a cut-off zip.
 */
fun interface EpubCheck {
    suspend fun opens(source: Source): Boolean
}
