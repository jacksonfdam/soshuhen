package app.soshuhen.core

import okio.Path
import okio.Source

/**
 * Unzipping is JVM code (ZipPages in jvmAndroidMain); the reader's state is
 * common code and only needs the pages it yields.
 */
fun interface PageExtractor {
    /**
     * [version] names the copy of the archive [source] reads, so pages cached
     * from a copy since replaced are extracted again rather than served.
     */
    suspend fun extract(chapterId: Long, version: String, source: Source): List<Path>
}
