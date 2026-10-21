package app.soshuhen.detail

import app.soshuhen.api.Resume
import app.soshuhen.api.SeriesDetail
import app.soshuhen.core.Availability
import app.soshuhen.core.ChapterRow
import app.soshuhen.core.chapterRows

fun continueChapter(detail: SeriesDetail, resume: Resume?, onDevice: Set<Long> = emptySet()): ChapterRow? {
    val rows = chapterRows(detail, onDevice)
    resume?.let { saved -> rows.firstOrNull { it.id == saved.chapterId }?.let { return it } }
    return rows.filter { !it.read && it.availability != Availability.NotDownloaded }.minByOrNull { it.number }
}
