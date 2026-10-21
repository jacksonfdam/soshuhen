package app.soshuhen.api

import io.ktor.utils.io.ByteReadChannel
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Values are the server's `PrefsIn`: mode paged_ltr | paged_rtl | long_strip | double,
 * scale fit_width | fit_height | fit_screen, background black | gray | white.
 * Strings rather than enums so a value a newer server adds still parses.
 */
@Serializable
data class ReaderPrefs(
    val mode: String,
    val scale: String,
    val background: String,
    // Read-only: tells whether this series overrides the defaults. The server
    // does not accept it back, so it is never part of a PUT.
    val custom: Boolean = false,
)

@Serializable
data class ChapterRef(val id: Long, val number: Double)

@Serializable
data class Manifest(
    @SerialName("page_count") val pageCount: Int,
    val previous: ChapterRef? = null,
    val next: ChapterRef? = null,
    val position: Int? = null,
)

/**
 * [body] is only valid inside the `read` block of [SoshuhenApi.archive]: the
 * connection closes when the block returns.
 */
data class ArchiveDownload(
    val body: ByteReadChannel,
    val etag: String?,
    val total: Long?,
    // The server ignored the Range and sent the whole file, so the bytes
    // already on disk are not a prefix of what is coming.
    val restarted: Boolean,
)
