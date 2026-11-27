package app.soshuhen.api

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.time.Instant

private const val PROFILE_HEADER = "X-Soshuhen-Profile"

private const val PROFILES = """
[{"id":1,"name":"Me","avatar":"avatar-01","has_pin":false,"is_manager":true,"position":0},
 {"id":7,"name":"Ana","avatar":"avatar-12","has_pin":true,"is_manager":false,"position":1}]
"""

class SoshuhenApiProfileTest {
    private val seen = mutableListOf<HttpRequestData>()

    private fun client(body: String = "[]") = soshuhenHttpClient(
        MockEngine { request ->
            seen += request
            respond(body, headers = headersOf(HttpHeaders.ContentType, "application/json"))
        },
    )

    @Test
    fun noHeaderForTheManager() = runTest {
        SoshuhenApi("http://s", client()).series()
        assertEquals(null, seen.single().headers[PROFILE_HEADER])
    }

    @Test
    fun everyRequestCarriesTheProfile() = runTest {
        val api = SoshuhenApi("http://s", client("{}"), profileKey = 7)
        runCatching { api.series() }
        api.putPosition(1, 2, 3, Instant.parse("2026-11-27T10:00:00Z"))
        api.complete(2, Instant.parse("2026-11-27T10:00:00Z"))
        assertEquals(listOf("7", "7", "7"), seen.map { it.headers[PROFILE_HEADER] })
    }

    @Test
    fun forProfileSwitchesOnlyTheCopy() = runTest {
        val api = SoshuhenApi("http://s", client())
        api.forProfile(7).series()
        api.series()
        assertEquals(listOf("7", null), seen.map { it.headers[PROFILE_HEADER] })
    }

    @Test
    fun unlockReadsOk() = runTest {
        val api = SoshuhenApi("http://s", client("""{"ok":false}"""))
        assertFalse(api.unlock(7, "1234"))
        val request = seen.single()
        assertEquals("/api/profiles/7/unlock", request.url.encodedPath)
        assertEquals("""{"pin":"1234"}""", request.body.toByteArray().decodeToString())
    }

    @Test
    fun profilesDecode() = runTest {
        val profiles = SoshuhenApi("http://s", client(PROFILES)).profiles()
        assertEquals(listOf(0L, 7L), profiles.map { it.key() })
        assertEquals(true, profiles[1].hasPin)
    }
}
