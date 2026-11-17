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

    /** Bytes in each series folder under `Soshuhen/`, by folder name, whoever put the files there. */
    suspend fun usage(): Map<String, Long>
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

/** A create the provider refused for a reason other than a full disk, or one it did not say. */
class CannotCreate(val name: String) : Exception("Cannot create $name")

// Under this, the card has no room for even one chapter archive. Above it, a
// refused create is something else, and "Device full" would send the user
// deleting chapters for nothing.
const val LOW_SPACE_BYTES = 64L * 1024 * 1024

/**
 * A provider refuses to create a file or folder with nothing but a null, on a
 * full card and on a card being ejected or swapped alike. The folder still being
 * there tells it apart from a lost folder; only the free space the volume reports
 * says whether the card is full. A Galaxy Tab once showed "Device full" with
 * 109 GB free because the null alone was taken to mean it.
 */
fun refusedToCreate(folderAvailable: Boolean, freeBytes: Long?, name: String): Exception = when {
    !folderAvailable -> FolderUnavailable("Cannot create $name")
    freeBytes != null && freeBytes < LOW_SPACE_BYTES -> DeviceFull()
    else -> CannotCreate(name)
}
