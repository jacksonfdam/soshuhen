package app.soshuhen.server

import app.soshuhen.api.Identity
import app.soshuhen.api.SoshuhenApi
import io.ktor.client.HttpClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds

data class FoundServer(val address: ServerAddress, val identity: Identity)

/** Asks every host whether it is a Soshuhen server. */
class ServerScanner(private val probe: suspend (ServerAddress) -> Identity?) {
    fun scan(
        hosts: List<String>,
        port: Int = 8080,
        concurrency: Int = 32,
        perHostTimeout: Duration = 800.milliseconds,
    ): Flow<FoundServer> = channelFlow {
        val permits = Semaphore(concurrency)
        for (host in hosts) {
            launch {
                permits.withPermit {
                    val address = ServerAddress("http", host, port)
                    val found = withTimeoutOrNull(perHostTimeout) { safely { probe(address) } }
                    // /api/health answers ok on anything; only the app name
                    // says this is the server and not a router or a NAS.
                    if (found != null && found.app == "soshuhen") send(FoundServer(address, found))
                }
            }
        }
    }
}

/** A probe that reads `/api/identity` and treats any failure as "not here". */
fun identityProbe(client: HttpClient): suspend (ServerAddress) -> Identity? = { address ->
    safely { SoshuhenApi(address.baseUrl, client).identity() }
}

private suspend fun <T> safely(block: suspend () -> T): T? = try {
    block()
} catch (e: CancellationException) {
    throw e
} catch (_: Exception) {
    null
}
