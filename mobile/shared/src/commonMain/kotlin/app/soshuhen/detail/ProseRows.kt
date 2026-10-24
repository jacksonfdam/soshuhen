package app.soshuhen.detail

import app.soshuhen.api.SeriesDetail
import app.soshuhen.core.Availability
import app.soshuhen.core.ChapterRow
import app.soshuhen.core.chapterRows
import app.soshuhen.core.volumeTitle
import app.soshuhen.core.volumesRead
import kotlin.math.floor

/** A light novel volume as the series screen lists it. [id] is null on a server that does not name volumes yet. */
data class VolumeRow(
    val id: Long?,
    val number: Double,
    val title: String?,
    val read: Boolean,
    val availability: Availability,
)

/** A web novel volume's chapters; [volume] is null for the chapters no volume's range covers. */
data class WebGroup(val volume: Double?, val rows: List<ChapterRow>)

/** [editions] holds "light" and/or "web", in that order, for the ones the series has. */
data class ProseRows(val editions: List<String>, val light: List<VolumeRow>, val web: List<WebGroup>)

const val LIGHT = "light"
const val WEB = "web"

/**
 * A novel's two editions laid out side by side. Volumes read in reading order,
 * oldest first: a novel is read from its first volume, unlike a manga's newest
 * chapter first.
 */
fun proseRows(
    detail: SeriesDetail,
    onDeviceChapters: Set<Long>,
    onDeviceVolumes: Set<Long>,
    volumeProgress: Int?,
): ProseRows {
    val read = volumesRead(detail, volumeProgress)
    val light = detail.volumes.filter { it.edition == LIGHT }.sortedBy { it.number }.map {
        VolumeRow(
            id = it.id,
            number = it.number,
            title = volumeTitle(it.number, it.title),
            read = floor(it.number) <= read,
            availability = when {
                it.id != null && it.id in onDeviceVolumes -> Availability.OnDevice
                it.id != null && it.readable -> Availability.OnServer
                else -> Availability.NotDownloaded
            },
        )
    }
    val chapters = chapterRows(detail, onDeviceChapters).sortedBy { it.number }
    val ranges = detail.volumes
        .filter { it.edition == WEB && it.firstPart != null && it.lastPart != null }
        .sortedBy { it.number }
    // First range wins: two volumes sharing a boundary chapter would otherwise
    // list it twice, and the list keys its rows by chapter id.
    val covered = mutableSetOf<Long>()
    val grouped = ranges.map { v ->
        WebGroup(v.number, chapters.filter { it.number >= v.firstPart!! && it.number <= v.lastPart!! && covered.add(it.id) })
    }
    val others = chapters.filter { it.id !in covered }
    val web = (grouped + if (others.isNotEmpty()) listOf(WebGroup(null, others)) else emptyList())
        .filter { it.rows.isNotEmpty() }
    val editions = listOfNotNull(LIGHT.takeIf { light.isNotEmpty() }, WEB.takeIf { web.isNotEmpty() })
    return ProseRows(editions, light, web)
}

/** Light first when there is any: it is the edition the lists count volumes in. */
fun defaultEdition(rows: ProseRows): String = rows.editions.firstOrNull() ?: LIGHT

/** The first unread volume there is a file of, here or on the server. */
fun continueVolume(rows: ProseRows): VolumeRow? =
    rows.light.firstOrNull { !it.read && it.id != null && it.availability != Availability.NotDownloaded }

fun volumeReadableFrom(row: VolumeRow, home: Boolean): Boolean =
    row.id != null && (row.availability == Availability.OnDevice || (home && row.availability == Availability.OnServer))
