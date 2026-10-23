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
    // What the web's cover card and series header show beside the cover.
    val format: String? = null,
    val genres: List<String> = emptyList(),
    val state: String? = null,
    val score: Double? = null,
    val providers: List<String> = emptyList(),
    @SerialName("auto_download") val autoDownload: Boolean = false,
    @SerialName("source_site") val sourceSite: String? = null,
)

@Serializable
data class SeriesChapter(
    val id: Long,
    val number: Double,
    val title: String? = null,
    val state: String,
    @SerialName("file_path") val filePath: String? = null,
)

/**
 * A volume of a novel. A `light` one owns one EPUB; a `web` one is only the
 * range of chapters that make it up. Every field past [edition] defaults, so a
 * server from before volumes carried them still decodes.
 */
@Serializable
data class SeriesVolume(
    val id: Long? = null,
    val number: Double,
    val edition: String,
    val title: String? = null,
    val state: String? = null,
    @SerialName("file_path") val filePath: String? = null,
    @SerialName("first_part") val firstPart: Double? = null,
    @SerialName("last_part") val lastPart: Double? = null,
    // The file is on disk inside the library, which is what the archive route serves.
    val readable: Boolean = false,
)

/** A list's own record of the series; only the volume count is read, for light novel volumes. */
@Serializable
data class SeriesEntry(
    val provider: String,
    @SerialName("user_progress_volume") val userProgressVolume: Int? = null,
)

@Serializable
data class Credit(val role: String, val name: String)

/** The provider metadata the web's series header and progress card read. */
@Serializable
data class SeriesMetadata(
    @SerialName("native_title") val nativeTitle: String? = null,
    @SerialName("publication_status") val publicationStatus: String? = null,
    @SerialName("start_year") val startYear: Int? = null,
    @SerialName("end_year") val endYear: Int? = null,
    val country: String? = null,
    val demographic: String? = null,
    val publisher: String? = null,
    val credits: List<Credit> = emptyList(),
    @SerialName("volumes_total") val volumesTotal: Int? = null,
    @SerialName("volumes_read") val volumesRead: Int? = null,
    @SerialName("reread_count") val rereadCount: Int? = null,
    // Dates as the provider wrote them: a day, not an instant.
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("completed_at") val completedAt: String? = null,
    @SerialName("list_updated_at") val listUpdatedAt: Instant? = null,
)

@Serializable
data class SeriesDetail(
    val series: Series,
    val chapters: List<SeriesChapter>,
    val volumes: List<SeriesVolume> = emptyList(),
    val entries: List<SeriesEntry> = emptyList(),
    val metadata: SeriesMetadata = SeriesMetadata(),
    @SerialName("reading_minutes_per_chapter") val readingMinutesPerChapter: Int? = null,
)

@Serializable
data class Resume(
    @SerialName("chapter_id") val chapterId: Long,
    val page: Int,
)
