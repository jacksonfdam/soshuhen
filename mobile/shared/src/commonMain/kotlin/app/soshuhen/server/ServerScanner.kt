package app.soshuhen.server

import app.soshuhen.api.Identity
import app.soshuhen.api.SoshuhenApi
import io.ktor.client.HttpClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds

data class FoundServer(val address: ServerAddress, val identity: Identity)

/** Asks every host whether it is a Soshuhen server. */
class ServerScanner(private val probe: suspend (ServerAddress) -> Identity?) {
    /**
     * [retryTimeout]: a host that did not answer within [perHostTimeout] is asked
     * once more with this long, null to skip. On a fresh install the scan is the
     * process's first traffic, and the HTTP client's cold start ate the whole
     * limit of the first probes: the server went unfound until "Scan again".
     * [warmUp]: a host asked first and never listed (the device's own address),
     * so the client is started before the limits begin to count.
     */
    fun scan(
        hosts: List<String>,
        port: Int = 8080,
        concurrency: Int = 32,
        perHostTimeout: Duration = 800.milliseconds,
        retryTimeout: Duration? = null,
        warmUp: String? = null,
    ): Flow<FoundServer> = channelFlow {
        warmUp?.let { host ->
            withTimeoutOrNull(retryTimeout ?: perHostTimeout) { safely { probe(ServerAddress("http", host, port)) } }
        }
        val permits = Semaphore(concurrency)

        // The hosts that ran out of time, as opposed to those that answered or refused.
        suspend fun pass(batch: List<String>, limit: Duration): List<String> = coroutineScope {
            batch.map { host ->
                async {
                    permits.withPermit {
                        val address = ServerAddress("http", host, port)
                        val answer = withTimeoutOrNull(limit) { Answer(safely { probe(address) }) }
                        val found = answer?.identity
                        // /api/health answers ok on anything; only the app name
                        // says this is the server and not a router or a NAS.
                        if (found != null && found.app == "soshuhen") send(FoundServer(address, found))
                        host.takeIf { answer == null }
                    }
                }
            }.awaitAll().filterNotNull()
        }

        val slow = pass(hosts, perHostTimeout)
        if (retryTimeout != null && slow.isNotEmpty()) pass(slow, retryTimeout)
    }
}

private class Answer(val identity: Identity?)

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
