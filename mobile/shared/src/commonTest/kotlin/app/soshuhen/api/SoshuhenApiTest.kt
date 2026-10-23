package app.soshuhen.api

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.http.HttpMethod
import io.ktor.client.engine.mock.toByteArray
import kotlinx.coroutines.test.runTest
import kotlin.time.Instant
import kotlin.test.assertTrue
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class SoshuhenApiTest {
    private fun api(body: String, status: HttpStatusCode = HttpStatusCode.OK): SoshuhenApi {
        val engine = MockEngine {
            respond(body, status, headersOf(HttpHeaders.ContentType, "application/json"))
        }
        return SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
    }

    @Test
    fun parsesTheLibraryIncludingNulls() = runTest {
        val rows = api(Fixtures.SERIES).series()
        assertEquals(2, rows.size)
        assertNotNull(rows[0].updatedAt)
        assertEquals(241, rows[0].totalChapters)
        assertNull(rows[1].coverUrl)
        assertNull(rows[1].totalChapters)
        assertNull(rows[1].lastReadAt)
        assertNull(rows[1].status)
    }

    @Test
    fun parsesSeriesDetailChapters() = runTest {
        val detail = api(Fixtures.DETAIL).seriesDetail(1)
        assertEquals(listOf(1.0, 2.0, 2.5), detail.chapters.map { it.number })
        assertNull(detail.chapters[1].filePath)
        assertNotNull(detail.series.lastReadAt)
    }

    @Test
    fun identityParses() = runTest {
        assertEquals("soshuhen", api(Fixtures.IDENTITY).identity().app)
    }

    @Test
    fun resumeIsNullWhenTheServerHasNone() = runTest {
        assertNull(api("", HttpStatusCode.NotFound).resume(1))
    }

    @Test
    fun aServerErrorIsAnApiException() = runTest {
        val error = assertFailsWith<ApiException> {
            api("", HttpStatusCode.InternalServerError).series()
        }
        assertEquals(500, error.status)
    }

    @Test
    fun coverUrlPointsAtTheServerNotTheCdn() {
        assertEquals("http://10.0.0.5:8080/api/series/7/cover", api("").coverUrl(7))
    }

    private fun recording(status: HttpStatusCode, requests: MutableList<HttpRequestData>): SoshuhenApi {
        val engine = MockEngine { request ->
            requests += request
            respond("PK", status, headersOf(HttpHeaders.ETag, "\"abc\""))
        }
        return SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
    }

    @Test
    fun archiveAsksForTheRemainder() = runTest {
        val requests = mutableListOf<HttpRequestData>()
        val restarted = recording(HttpStatusCode.PartialContent, requests)
            .archive(7, from = 100) { it.restarted }
        assertEquals("bytes=100-", requests.single().headers[HttpHeaders.Range])
        assertEquals("/api/chapters/7/archive", requests.single().url.encodedPath)
        assertEquals(false, restarted)
    }

    @Test
    fun archiveA200ToARangeMeansStartOver() = runTest {
        val restarted = recording(HttpStatusCode.OK, mutableListOf()).archive(7, from = 100) { it.restarted }
        assertEquals(true, restarted)
    }

    @Test
    fun archiveFromZeroSendsNoRangeAndReadsTheEtag() = runTest {
        val requests = mutableListOf<HttpRequestData>()
        val etag = recording(HttpStatusCode.OK, requests).archive(7, from = 0) { it.etag }
        assertNull(requests.single().headers[HttpHeaders.Range])
        assertEquals("\"abc\"", etag)
    }

    @Test
    fun volumeArchiveAsksTheVolumeRouteForTheRemainder() = runTest {
        val requests = mutableListOf<HttpRequestData>()
        val etag = recording(HttpStatusCode.PartialContent, requests)
            .volumeArchive(7, from = 10, ifRange = "\"old\"") { it.etag }
        assertEquals("/api/volumes/7/archive", requests.single().url.encodedPath)
        assertEquals("bytes=10-", requests.single().headers[HttpHeaders.Range])
        assertEquals("\"old\"", requests.single().headers[HttpHeaders.IfRange])
        assertEquals("\"abc\"", etag)
    }

    @Test
    fun completeVolumePostsWhenItWasRead() = runTest {
        val requests = mutableListOf<HttpRequestData>()
        recording(HttpStatusCode.OK, requests).completeVolume(7, Instant.parse("2026-10-24T08:00:00Z"))
        assertEquals("/api/reader/volumes/7/complete", requests.single().url.encodedPath)
        assertEquals(HttpMethod.Post, requests.single().method)
        assertTrue(String(requests.single().body.toByteArray()).contains("\"read_at\":\"2026-10-24T08:00:00Z\""))
    }

    @Test
    fun decodesVolumesWithTheFieldsTheAppCopiesBy() = runTest {
        val detail = api(Fixtures.PROSE_DETAIL).seriesDetail(308)
        val volume = detail.volumes.single()
        assertEquals(41L, volume.id)
        assertEquals("light", volume.edition)
        assertEquals("/manga/tsuki/tsuki - Vol.0001.epub", volume.filePath)
        assertEquals(true, volume.readable)
        assertEquals(3, detail.entries.single().userProgressVolume)
    }

    // The shape main serves before the web session adds id and file_path.
    @Test
    fun decodesVolumesWithoutThem() = runTest {
        val detail = api(Fixtures.PROSE_DETAIL_OLD).seriesDetail(308)
        val volume = detail.volumes.single()
        assertNull(volume.id)
        assertNull(volume.filePath)
        assertEquals(false, volume.readable)
    }

    @Test
    fun anArchiveTheServerRefusesIsAnApiException() = runTest {
        val error = assertFailsWith<ApiException> {
            recording(HttpStatusCode.NotFound, mutableListOf()).archive(7, from = 0) { }
        }
        assertEquals(404, error.status)
    }

    @Test
    fun prefsParse() = runTest {
        val prefs = api("""{"mode":"double","scale":"fit_height","background":"white","custom":true}""").prefs(1)
        assertEquals(ReaderPrefs("double", "fit_height", "white", custom = true), prefs)
    }

    @Test
    fun manifestParsesNeighboursAndPosition() = runTest {
        val m = api(
            """{"page_count":24,"previous":{"id":4,"number":1.0,"title":null,"state":"downloaded"},
               "next":null,"position":9,"origin":"archive"}""",
        ).manifest(5)
        assertEquals(24, m.pageCount)
        assertEquals(4L, m.previous!!.id)
        assertNull(m.next)
        assertEquals(9, m.position)
    }

    @Test
    fun pageUrlIsBuiltOnTheServer() {
        assertEquals(
            "http://10.0.0.5:8080/api/reader/chapters/5/pages/3",
            api("").pageUrl(5, 3),
        )
    }
}

class RedirectTest {
    @Test
    fun aRedirectIsNotFollowedOffTheNetwork() = runTest {
        val hosts = mutableListOf<String>()
        val engine = MockEngine { request ->
            hosts += request.url.host
            respond("", HttpStatusCode.Found, headersOf(HttpHeaders.Location, "http://portal.example.com/login"))
        }
        val api = SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
        assertEquals(302, assertFailsWith<ApiException> { api.identity() }.status)
        assertEquals(listOf("10.0.0.5"), hosts)
    }
}
