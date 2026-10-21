package app.soshuhen.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlin.time.Instant

// Only the fields the app reads. The server sends many more, and a field it
// adds later must not break a phone nobody has updated.

@Serializable
data class Identity(
    val app: String,
    val name: String,
    val version: String,
    @SerialName("instance_id") val instanceId: String,
)

@Serializable
data class Series(
    val id: Long,
    val title: String,
    val slug: String,
    @SerialName("cover_url") val coverUrl: String? = null,
    val downloaded: Int = 0,
    val known: Int = 0,
    @SerialName("total_chapters") val totalChapters: Int? = null,
    val kind: String? = null,
    val status: String? = null,
    val progress: Int = 0,
    @SerialName("last_read_at") val lastReadAt: Instant? = null,
    @SerialName("updated_at") val updatedAt: Instant? = null,
)

@Serializable
data class SeriesChapter(
    val id: Long,
    val number: Double,
    val title: String? = null,
    val state: String,
    @SerialName("file_path") val filePath: String? = null,
)

@Serializable
data class SeriesDetail(
    val series: Series,
    val chapters: List<SeriesChapter>,
)

@Serializable
data class Resume(
    @SerialName("chapter_id") val chapterId: Long,
    val page: Int,
)
