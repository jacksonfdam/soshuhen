package app.soshuhen.core

import app.soshuhen.api.Series

/** One series folder: [seriesId] is null when no series the server lists has that slug. */
data class FolderUse(val seriesId: Long?, val title: String, val bytes: Long, val marked: Boolean)

/**
 * What the picked folder holds. Measured from the folder itself: the index
 * knows only the marked series' chapters, and a card holding 14 GB once read
 * as 5.3 GB used because everything else in the folder went uncounted.
 */
data class FolderStorage(val used: Long, val notMarked: Long, val perSeries: List<FolderUse>)

fun folderStorage(bySlug: Map<String, Long>, series: List<Series>, marked: Set<Long>): FolderStorage {
    val known = series.associateBy { it.slug }
    val uses = bySlug.map { (slug, bytes) ->
        val s = known[slug]
        FolderUse(s?.id, s?.title ?: slug, bytes, s != null && s.id in marked)
    }.sortedByDescending { it.bytes }
    return FolderStorage(uses.sumOf { it.bytes }, uses.filterNot { it.marked }.sumOf { it.bytes }, uses)
}
