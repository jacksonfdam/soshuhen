package app.soshuhen.core

import okio.Sink
import okio.Source

/** The folder the user picked, as the one place chapter files live: `<picked>/Soshuhen/<slug>/<file>`. */
interface ChapterFolder {
    /** The tree URI still holds its permission and exists. */
    fun isAvailable(): Boolean

    suspend fun write(slug: String, fileName: String, append: Boolean, block: suspend (Sink) -> Unit)

    suspend fun size(slug: String, fileName: String): Long?

    /** The file's URI, or null when there is no such file; a `.part` can only be read or deleted by URI. */
    suspend fun find(slug: String, fileName: String): String?

    /** Returns the renamed file's URI, which is what the index keeps. */
    suspend fun rename(slug: String, from: String, to: String): String

    suspend fun delete(uri: String)

    suspend fun exists(uri: String): Boolean

    suspend fun read(uri: String): Source
}

/** The permission was revoked or the folder is gone: nothing can be read or written. */
class FolderUnavailable(message: String? = null) : Exception(message)

class DeviceFull : Exception()

/** One file is missing from a folder that is otherwise fine, as when the user removed it by hand. */
class ChapterFileMissing : Exception()

/**
 * The mode a chapter file is opened in for writing. Since API 29 a plain "w"
 * no longer truncates: a restarted copy over a longer `.part` kept the old
 * tail, failed its length check as a lost server, and wasted the run.
 */
fun writeMode(append: Boolean): String = if (append) "wa" else "wt"

/**
 * A provider refuses to create a file or folder on a full card with nothing but
 * a null, which alone reads like a folder that went away; the folder still being
 * there is what tells the two apart, and decides which banner the user sees.
 */
fun refusedToCreate(folderAvailable: Boolean, name: String): Exception =
    if (folderAvailable) DeviceFull() else FolderUnavailable("Cannot create $name")
