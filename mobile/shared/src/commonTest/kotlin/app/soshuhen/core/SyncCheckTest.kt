package app.soshuhen.core

import app.soshuhen.api.Series
import app.soshuhen.api.SeriesChapter
import app.soshuhen.api.SeriesDetail
import app.soshuhen.api.SeriesVolume
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant

private val AT = Instant.fromEpochMilliseconds(1_000)
private val SERIES = Series(id = 1, title = "Frieren", slug = "frieren")

private fun ch(id: Long, state: String = "downloaded") =
    SeriesChapter(id, id.toDouble(), state = state, filePath = if (state == "downloaded") "/manga/frieren/c$id.cbz" else null)

private fun held(id: Long, etag: String? = "\"e$id\"", size: Long = 100) =
    DeviceChapter(id, 1, id.toDouble(), "c$id.cbz", "mem://c$id", etag, size, AT)

private fun device(vararg chapters: DeviceChapter, gone: Set<String> = emptySet(), sizes: Map<String, Long> = emptyMap()) =
    DeviceState(
        chapters = chapters.associateBy { it.chapterId },
        volumes = emptyMap(),
        actualSize = chapters.associate { it.uri to if (it.uri in gone) null else (sizes[it.uri] ?: it.size) },
    )

class SyncCheckTest {
    @Test fun sync_report_all_verified() {
        val r = checkSync(listOf(SeriesDetail(SERIES, listOf(ch(1), ch(2)))), device(held(1), held(2)))
        assertTrue(r.allVerified)
        assertEquals(200L, r.bytes)
        assertEquals(1, r.seriesCount)
    }

    @Test fun sync_report_blocks_when_not_copied() {
        val r = checkSync(listOf(SeriesDetail(SERIES, listOf(ch(1), ch(2)))), device(held(1)))
        assertEquals(Missing(BookRef(BookKind.Chapter, 2), MissingReason.NotCopied), r.missing.single())
        assertFalse(r.allVerified)
    }

    @Test fun sync_report_blocks_when_file_missing() {
        val r = checkSync(listOf(SeriesDetail(SERIES, listOf(ch(1), ch(2)))), device(held(1), held(2), gone = setOf("mem://c2")))
        assertEquals(MissingReason.FileGone, r.missing.single().reason)
        assertFalse(r.allVerified)
    }

    @Test fun sync_report_blocks_on_size_mismatch() {
        val r = checkSync(listOf(SeriesDetail(SERIES, listOf(ch(1)))), device(held(1), sizes = mapOf("mem://c1" to 7L)))
        assertEquals(MissingReason.SizeMismatch, r.missing.single().reason)
    }

    @Test fun sync_report_blocks_on_null_or_unreadable_etag() {
        val r = checkSync(
            listOf(SeriesDetail(SERIES, listOf(ch(1), ch(2)))),
            device(held(1, etag = null), held(2, etag = UNREADABLE_ETAG)),
        )
        assertEquals(listOf(MissingReason.NoEtag, MissingReason.Unreadable), r.missing.map { it.reason })
    }

    @Test fun sync_report_ignores_offloaded_and_not_downloaded() {
        val r = checkSync(
            listOf(SeriesDetail(SERIES, listOf(ch(1), ch(2, "offloaded"), ch(3, "known")))),
            device(held(1), held(2)),
        )
        assertEquals(listOf(1L), r.held.map { it.ref.id })
        assertTrue(r.allVerified)
    }

    @Test fun sync_report_with_nothing_on_the_server_offers_nothing() {
        val r = checkSync(listOf(SeriesDetail(SERIES, listOf(ch(1, "offloaded")))), device(held(1)))
        assertFalse(r.allVerified)
    }

    @Test fun sync_report_checks_light_volumes() {
        val volume = SeriesVolume(id = 9, number = 1.0, edition = "light", state = "downloaded",
            filePath = "/manga/f/v1.epub", readable = true)
        val onDevice = DeviceVolume(9, 1, 1.0, "v1.epub", "mem://v9", "\"v\"", 500, AT)
        val r = checkSync(
            listOf(SeriesDetail(SERIES, emptyList(), volumes = listOf(volume))),
            DeviceState(emptyMap(), mapOf(9L to onDevice), mapOf("mem://v9" to 500L)),
        )
        assertEquals(Held(BookRef(BookKind.Volume, 9), "\"v\"", 500), r.held.single())
    }

    @Test fun sync_report_lists_revised_offloaded_volumes() {
        val volume = SeriesVolume(id = 9, number = 1.0, edition = "light", state = "offloaded", revised = true)
        val r = checkSync(listOf(SeriesDetail(SERIES, listOf(ch(1)), volumes = listOf(volume))), device(held(1)))
        assertEquals(listOf(9L), r.revised)
        assertTrue(r.allVerified)
    }

    @Test fun offload_request_splits_chapters_and_volumes() {
        val report = SyncReport(1, listOf(Held(BookRef(BookKind.Chapter, 1), "\"a\"", 10), Held(BookRef(BookKind.Volume, 9), "\"b\"", 20)), emptyList(), emptyList())
        val request = report.offloadRequest()
        assertEquals(listOf(1L), request.chapters.map { it.id })
        assertEquals(listOf(9L), request.volumes.map { it.id })
    }
}
