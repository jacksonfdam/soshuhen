package app.soshuhen.core

import app.soshuhen.server.ServerLocator
import app.soshuhen.server.ServerScanner
import app.soshuhen.server.identityProbe
import io.ktor.client.HttpClient
import kotlinx.coroutines.CoroutineScope
import okio.Path

/**
 * Every long-lived object the screens share, built once by the platform.
 * A dozen objects do not need a dependency injection framework.
 */
class AppGraph(
    val store: ServerStore,
    val network: NetworkInfo,
    val client: HttpClient,
    scope: CoroutineScope,
    val local: LocalStore,
    // The platform's cache directory, which common code cannot name itself.
    val cacheDir: Path,
) {
    val probe = identityProbe(client)
    val scanner = ServerScanner(probe)
    val session = Session(store, ServerLocator(probe, scanner), network, client, scope)
}
