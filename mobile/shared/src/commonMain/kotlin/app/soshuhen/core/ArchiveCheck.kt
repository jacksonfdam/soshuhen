package app.soshuhen.core

import okio.Source

/**
 * Whether a copied archive can be read, before it takes a chapter's place on
 * the device. A cut-off zip still has a name and a size; only its pages tell.
 * Zero pages, or a throw, fails the check.
 */
fun interface ArchiveCheck {
    suspend fun pageCount(source: Source): Int
}
