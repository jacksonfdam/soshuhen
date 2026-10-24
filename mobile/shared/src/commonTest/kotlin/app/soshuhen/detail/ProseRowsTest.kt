package app.soshuhen.detail

import app.soshuhen.api.Series
import app.soshuhen.api.SeriesChapter
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SeriesEntry
import app.soshuhen.api.SeriesVolume
import app.soshuhen.core.Availability
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ProseRowsTest {
    private val novel = Series(id = 308, title = "Tsukimichi", slug = "tsuki", kind = "prose")

    private fun light(id: Long, number: Double, readable: Boolean = true) =
        SeriesVolume(id = id, number = number, edition = "light", state = "downloaded", filePath = "/v$id.epub", readable = readable)

    private fun web(id: Long, number: Double, first: Double?, last: Double?) =
        SeriesVolume(id = id, number = number, edition = "web", firstPart = first, lastPart = last)

    private fun chapter(id: Long, number: Double) =
        SeriesChapter(id, number, state = "downloaded", filePath = "/c$id.epub")

    @Test fun series308ListsTwentyLightVolumesInOrder() {
        val detail = SeriesDetail(novel, emptyList(), volumes = (20 downTo 1).map { light(it.toLong(), it.toDouble()) })
        val rows = proseRows(detail, emptySet(), emptySet(), null)
        assertEquals(listOf("light"), rows.editions)
        assertEquals((1..20).map { it.toDouble() }, rows.light.map { it.number })
        assertEquals(Availability.OnServer, rows.light.first().availability)
        assertEquals("light", defaultEdition(rows))
    }

    @Test fun deviceAndServerAvailabilityOfVolumes() {
        val detail = SeriesDetail(
            novel, emptyList(),
            volumes = listOf(light(1, 1.0), light(2, 2.0, readable = false), SeriesVolume(id = null, number = 3.0, edition = "light", readable = true)),
        )
        val rows = proseRows(detail, emptySet(), setOf(1L), null)
        assertEquals(listOf(Availability.OnDevice, Availability.NotDownloaded, Availability.NotDownloaded), rows.light.map { it.availability })
        // A volume the server cannot name cannot be opened, but it is still the user's to see.
        assertNull(rows.light[2].id)
    }

    @Test fun webChaptersGroupUnderTheirVolumeRange() {
        val detail = SeriesDetail(
            novel, (1..6).map { chapter(it.toLong(), it.toDouble()) } + chapter(7, 2.5),
            volumes = listOf(web(10, 1.0, 1.0, 3.0), web(11, 2.0, 4.0, 5.0)),
        )
        val rows = proseRows(detail, setOf(2L), emptySet(), null)
        assertEquals(listOf("web"), rows.editions)
        assertEquals(listOf(1.0, 2.0, null), rows.web.map { it.volume })
        assertEquals(listOf(1.0, 2.0, 2.5, 3.0), rows.web[0].rows.map { it.number })
        assertEquals(Availability.OnDevice, rows.web[0].rows[1].availability)
        // Chapters outside every range go under "Other chapters".
        assertEquals(listOf(6.0), rows.web[2].rows.map { it.number })
        assertEquals("web", defaultEdition(rows))
    }

    @Test fun aVolumeIsReadByTheListsOrTheDevicesCount() {
        val detail = SeriesDetail(
            novel, emptyList(),
            volumes = listOf(light(1, 1.0), light(2, 2.0), light(3, 3.0)),
            entries = listOf(SeriesEntry("mal", userProgressVolume = 1)),
        )
        assertEquals(listOf(true, false, false), proseRows(detail, emptySet(), emptySet(), null).light.map { it.read })
        assertEquals(listOf(true, true, false), proseRows(detail, emptySet(), emptySet(), 2).light.map { it.read })
    }

    @Test fun bothEditionsOfferBoth() {
        val detail = SeriesDetail(novel, listOf(chapter(1, 1.0)), volumes = listOf(light(1, 1.0), web(10, 1.0, 1.0, 1.0)))
        val rows = proseRows(detail, emptySet(), emptySet(), null)
        assertEquals(listOf("light", "web"), rows.editions)
        assertEquals("light", defaultEdition(rows))
    }

    @Test fun continueOpensTheFirstUnreadReadableVolume() {
        val detail = SeriesDetail(
            novel, emptyList(),
            volumes = listOf(light(1, 1.0), light(2, 2.0, readable = false), light(3, 3.0)),
            entries = listOf(SeriesEntry("mal", userProgressVolume = 1)),
        )
        val rows = proseRows(detail, emptySet(), emptySet(), null)
        assertEquals(3L, continueVolume(rows)?.id)
    }

    // Two ranges sharing a boundary must not list the chapter twice: the list keys rows by id.
    @Test fun aChapterInTwoRangesGoesUnderTheFirst() {
        val detail = SeriesDetail(
            novel, (9..11).map { chapter(it.toLong(), it.toDouble()) },
            volumes = listOf(web(10, 1.0, 1.0, 10.0), web(11, 2.0, 10.0, 20.0)),
        )
        val rows = proseRows(detail, emptySet(), emptySet(), null)
        assertEquals(listOf(listOf(9.0, 10.0), listOf(11.0)), rows.web.map { g -> g.rows.map { it.number } })
    }
}
