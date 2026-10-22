package app.soshuhen.core

import app.soshuhen.server.ServerLocator
import app.soshuhen.server.ServerScanner
import app.soshuhen.server.identityProbe
import app.soshuhen.reader.PageExtractor
import io.ktor.client.HttpClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import okio.Path
import kotlin.time.Clock

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
    val folder: ChapterFolder,
    // The platform's cache directory, which common code cannot name itself.
    val cacheDir: Path,
    archiveCheck: ArchiveCheck,
    // The same object as archiveCheck on Android, so the import check and the
    // reader share one extraction cache and one lock on it.
    val pages: PageExtractor,
) {
    val probe = identityProbe(client)
    val scanner = ServerScanner(probe)
    val library = DeviceLibrary(local, folder)
    val session = Session(store, ServerLocator(probe, scanner), network, client, scope)
    val outbox = Outbox(local) { Clock.System.now() }
    val importer = ImportRunner(session, local, folder, outbox, archiveCheck) { Clock.System.now() }

    // Read on every key press by the activity, which cannot wait for DataStore.
    val volumeKeys: StateFlow<Boolean> = store.volumeKeys.stateIn(scope, SharingStarted.Eagerly, true)
    val volumeInvert: StateFlow<Boolean> = store.volumeInvert.stateIn(scope, SharingStarted.Eagerly, false)
}
