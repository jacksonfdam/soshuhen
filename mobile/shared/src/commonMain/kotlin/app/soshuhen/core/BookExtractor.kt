package app.soshuhen.core

import okio.Path
import okio.Source

/**
 * Unzipping is JVM code (EpubFiles in jvmAndroidMain); the prose reader is
 * common code and only needs the directory the book was unpacked into.
 */
fun interface BookExtractor {
    /** [version] names the copy [source] reads, so a book replaced since is unpacked again. */
    suspend fun unpack(ref: BookRef, version: String, source: Source): Path
}
