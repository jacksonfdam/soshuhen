package app.soshuhen.server

import app.soshuhen.api.Identity
import app.soshuhen.api.SoshuhenApi
import app.soshuhen.api.soshuhenHttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

fun identity(app: String = "soshuhen", id: String = "id-1") = Identity(app, "Soshuhen", "0.1.0", id)

class ServerScannerTest {
    private fun scanner(answers: Map<String, suspend () -> Identity?>) =
        ServerScanner { address -> answers[address.host]?.invoke() }

    @Test fun findsOnlySoshuhen() = runTest {
        val found = scanner(mapOf("10.0.0.2" to { identity() }, "10.0.0.3" to { identity(app = "router") }))
            .scan(listOf("10.0.0.2", "10.0.0.3", "10.0.0.4")).toList()
        assertEquals(listOf("10.0.0.2"), found.map { it.address.host })
    }

    @Test fun aThrowingOrSlowHostIsSkipped() = runTest {
        val found = scanner(
            mapOf(
                "10.0.0.2" to { error("connection refused") },
                "10.0.0.3" to { delay(5_000); identity() },
                "10.0.0.4" to { identity() },
            ),
        ).scan(listOf("10.0.0.2", "10.0.0.3", "10.0.0.4")).toList()
        assertEquals(listOf("10.0.0.4"), found.map { it.address.host })
    }

    @Test fun nothingFoundCompletesEmpty() = runTest {
        assertTrue(scanner(emptyMap()).scan(subnetHosts("10.0.0.1", 24)).toList().isEmpty())
    }

    @Test fun anHtmlPageIsNotAServer() = runTest {
        val client = soshuhenHttpClient(MockEngine { respond("<html>router</html>", HttpStatusCode.OK) })
        assertNull(identityProbe(client)(ServerAddress("http", "10.0.0.1", 8080)))
    }

    @Test fun aServerErrorIsNotAServer() = runTest {
        val client = soshuhenHttpClient(MockEngine { respond("", HttpStatusCode.InternalServerError) })
        assertNull(identityProbe(client)(ServerAddress("http", "10.0.0.1", 8080)))
    }

    @Test fun unrelatedJsonIsNotAServer() = runTest {
        val client = soshuhenHttpClient(MockEngine { respond("""{"status":"ok"}""", HttpStatusCode.OK) })
        assertNull(identityProbe(client)(ServerAddress("http", "10.0.0.1", 8080)))
    }
}
