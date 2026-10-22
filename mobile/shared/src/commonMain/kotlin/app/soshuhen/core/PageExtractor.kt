package app.soshuhen.core

import okio.Path
import okio.Source

/**
 * Unzipping is JVM code (ZipPages in jvmAndroidMain); the reader's state is
 * common code and only needs the pages it yields.
 */
fun interface PageExtractor {
    suspend fun extract(chapterId: Long, source: Source): List<Path>
}
