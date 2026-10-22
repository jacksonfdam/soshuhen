package app.soshuhen.core

import app.soshuhen.api.ReaderPrefs
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.db.SoshuhenDatabase
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class OutboxTest {
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private var now = Instant.parse("2026-10-21T08:10:00Z")
    private lateinit var outbox: Outbox

    private class Sent(val method: HttpMethod, val path: String, val body: String)

    @BeforeTest fun setUp() {
        db = testDatabase()
        store = LocalStore(db)
        outbox = Outbox(store) { now }
    }

    @AfterTest fun tearDown() = db.close()

    private fun TestScope.apiAnswering(
        sent: MutableList<Sent>,
        answer: (Int, HttpRequestData) -> HttpStatusCode,
    ): SoshuhenApi {
        var n = 0
        val engine = MockEngine(
            MockEngineConfig().apply {
                dispatcher = StandardTestDispatcher(testScheduler)
                addHandler { request ->
                    sent += Sent(request.method, request.url.encodedPath, String(request.body.toByteArray()))
                    respond("{}", answer(n++, request), headersOf(HttpHeaders.ContentType, "application/json"))
                }
            },
        )
        return SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
    }

    private suspend fun queuedChapters() = store.outbox().map { it.chapterId }

    @Test fun positionsCoalescePerSeries() = runTest {
        outbox.position(1, 10, 3)
        outbox.position(1, 11, 5)
        outbox.position(2, 20, 1)
        val sent = mutableListOf<Sent>()
        val result = outbox.drain(apiAnswering(sent) { _, _ -> HttpStatusCode.OK })
        assertEquals(DrainResult(sent = 2, dropped = 0, remaining = 0), result)
        assertEquals(listOf("/api/reader/series/1/position", "/api/reader/series/2/position"), sent.map { it.path })
        assertTrue(sent[0].body.contains("\"chapter_id\":11"))
        assertTrue(sent[0].body.contains("\"page\":5"))
        assertTrue(sent.all { it.method == HttpMethod.Put })
    }

    @Test fun completionsAreSentOldestFirstWithTheirReadAt() = runTest {
        outbox.complete(1, 10)
        now = Instant.parse("2026-10-21T09:00:00Z")
        outbox.complete(1, 11)
        val sent = mutableListOf<Sent>()
        outbox.drain(apiAnswering(sent) { _, _ -> HttpStatusCode.OK })
        assertEquals(listOf("/api/reader/chapters/10/complete", "/api/reader/chapters/11/complete"), sent.map { it.path })
        assertTrue(sent[0].body.contains("2026-10-21T08:10:00Z"))
        assertTrue(sent[1].body.contains("2026-10-21T09:00:00Z"))
    }

    @Test fun a404DropsThatEventAndContinues() = runTest {
        outbox.complete(1, 10)
        outbox.complete(1, 11)
        val result = outbox.drain(
            apiAnswering(mutableListOf()) { n, _ -> if (n == 0) HttpStatusCode.NotFound else HttpStatusCode.OK },
        )
        assertEquals(DrainResult(sent = 1, dropped = 1, remaining = 0), result)
        assertTrue(store.outbox().isEmpty())
    }

    @Test fun aRateLimitOrRequestTimeoutIsRetriedNotDropped() = runTest {
        outbox.complete(1, 10)
        outbox.complete(1, 11)
        val result = outbox.drain(apiAnswering(mutableListOf()) { _, _ -> HttpStatusCode.TooManyRequests })
        assertEquals(DrainResult(sent = 0, dropped = 0, remaining = 2), result)
        val timedOut = outbox.drain(apiAnswering(mutableListOf()) { _, _ -> HttpStatusCode.RequestTimeout })
        assertEquals(DrainResult(sent = 0, dropped = 0, remaining = 2), timedOut)
        assertEquals(listOf(10L, 11L), queuedChapters())
    }

    @Test fun aServerErrorStopsAndKeepsTheRest() = runTest {
        outbox.complete(1, 10)
        outbox.complete(1, 11)
        val sent = mutableListOf<Sent>()
        val result = outbox.drain(apiAnswering(sent) { _, _ -> HttpStatusCode.InternalServerError })
        assertEquals(DrainResult(sent = 0, dropped = 0, remaining = 2), result)
        assertEquals(1, sent.size)
        assertEquals(listOf(10L, 11L), queuedChapters())
    }

    @Test fun aStopPartWayKeepsOnlyWhatWasNotSent() = runTest {
        outbox.complete(1, 10)
        outbox.complete(1, 11)
        outbox.complete(1, 12)
        val result = outbox.drain(
            apiAnswering(mutableListOf()) { n, _ -> if (n == 0) HttpStatusCode.OK else HttpStatusCode.BadGateway },
        )
        assertEquals(DrainResult(sent = 1, dropped = 0, remaining = 2), result)
        assertEquals(listOf(11L, 12L), queuedChapters())
    }

    @Test fun aTimeoutStopsAndKeepsTheRest() = runTest {
        outbox.complete(1, 10)
        outbox.complete(1, 11)
        val engine = MockEngine(
            MockEngineConfig().apply {
                dispatcher = StandardTestDispatcher(testScheduler)
                addHandler { throw HttpRequestTimeoutException("http://10.0.0.5", 15_000) }
            },
        )
        val api = SoshuhenApi("http://10.0.0.5:8080", soshuhenHttpClient(engine))
        assertEquals(DrainResult(sent = 0, dropped = 0, remaining = 2), outbox.drain(api))
        assertEquals(listOf(10L, 11L), queuedChapters())
    }

    @Test fun prefsReplacePerSeriesAndAreSentAsTheServerExpects() = runTest {
        outbox.prefs(1, ReaderPrefs("paged_ltr", "fit_width", "black"))
        outbox.prefs(1, ReaderPrefs("long_strip", "fit_screen", "gray", custom = true))
        val sent = mutableListOf<Sent>()
        outbox.drain(apiAnswering(sent) { _, _ -> HttpStatusCode.OK })
        assertEquals(1, sent.size)
        assertEquals("/api/reader/series/1/prefs", sent[0].path)
        assertTrue(sent[0].body.contains("\"mode\":\"long_strip\""))
    }

    @Test fun readAtIsUtcIso() = runTest {
        outbox.position(1, 10, 3)
        val sent = mutableListOf<Sent>()
        outbox.drain(apiAnswering(sent) { _, _ -> HttpStatusCode.OK })
        assertTrue(sent[0].body.contains("\"read_at\":\"2026-10-21T08:10:00Z\""), sent[0].body)
    }
}
