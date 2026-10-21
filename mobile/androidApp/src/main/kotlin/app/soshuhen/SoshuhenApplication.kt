package app.soshuhen

import android.app.Application
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.AndroidNetworkInfo
import app.soshuhen.core.AppGraph
import app.soshuhen.core.ArchiveCheck
import app.soshuhen.core.DataStoreServerStore
import app.soshuhen.core.ImportEnvironment
import app.soshuhen.core.ImportScheduler
import app.soshuhen.core.LocalStore
import app.soshuhen.core.Notifier
import app.soshuhen.core.SafChapterFolder
import app.soshuhen.db.databaseBuilder
import okio.Path.Companion.toPath
import okio.buffer
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn

class SoshuhenApplication : Application(), ImportEnvironment {
    // One per process: DataStore refuses two instances on the same file.
    override val graph: AppGraph by lazy {
        val database = databaseBuilder(this).build()
        val servers = DataStoreServerStore(this)
        val scope = MainScope()
        AppGraph(
            servers,
            AndroidNetworkInfo(this),
            soshuhenHttpClient(),
            scope,
            LocalStore(database),
            SafChapterFolder(this, servers.folder.stateIn(scope, SharingStarted.Eagerly, null)),
            cacheDir.absolutePath.toPath(),
            // TEMPORARY, replaced by the zip-based check in Task 6: it only
            // recognises the zip signature, so a cut-off archive that still
            // starts correctly would pass until then.
            ArchiveCheck { source ->
                val head = source.buffer().use { if (it.request(4)) it.readByteString(4) else null }
                if (head != null && head == ZIP_SIGNATURE) 1 else 0
            },
        )
    }

    override val notifier: Notifier by lazy { Notifier(this, R.drawable.ic_notification) }

    override fun onCreate() {
        super.onCreate()
        // Channels before anything can post: a notification to a channel that
        // does not exist is dropped without a word.
        notifier.createChannels()
        ImportScheduler.schedule(this)
    }

    private companion object {
        val ZIP_SIGNATURE = okio.ByteString.of(0x50, 0x4B, 0x03, 0x04)
    }
}
