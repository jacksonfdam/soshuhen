package app.soshuhen.core

import app.soshuhen.api.Series
import kotlin.test.Test
import kotlin.test.assertEquals

class FolderStorageTest {
    private val series = listOf(Series(1, "Frieren", "frieren"), Series(2, "Gin Tama", "gin-tama"))

    @Test fun usedIsWhatTheFolderHoldsNotWhatTheIndexKnows() {
        // A tablet's card held 14 GB while the index, which only knows the
        // marked series' chapters, said 5.3 GB.
        val s = folderStorage(mapOf("frieren" to 300L, "gin-tama" to 700L), series, marked = setOf(1))
        assertEquals(1000L, s.used)
    }

    @Test fun eachFolderIsNamedAfterItsSeriesLargestFirst() {
        val s = folderStorage(mapOf("frieren" to 300L, "gin-tama" to 700L), series, marked = setOf(1, 2))
        assertEquals(listOf("Gin Tama" to 700L, "Frieren" to 300L), s.perSeries.map { it.title to it.bytes })
        assertEquals(listOf(true, true), s.perSeries.map { it.marked })
    }

    @Test fun whatNoMarkedSeriesOwnsIsCountedApart() {
        val s = folderStorage(
            mapOf("frieren" to 300L, "gin-tama" to 700L, "old-renamed-slug" to 50L),
            series,
            marked = setOf(1),
        )
        assertEquals(750L, s.notMarked)
        val unknown = s.perSeries.single { it.title == "old-renamed-slug" }
        assertEquals(false, unknown.marked)
        assertEquals(null, unknown.seriesId)
    }

    @Test fun anEmptyFolderUsesNothing() {
        val s = folderStorage(emptyMap(), series, marked = emptySet())
        assertEquals(0L, s.used)
        assertEquals(0L, s.notMarked)
        assertEquals(emptyList(), s.perSeries)
    }
}
