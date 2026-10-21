package app.soshuhen.api

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
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
