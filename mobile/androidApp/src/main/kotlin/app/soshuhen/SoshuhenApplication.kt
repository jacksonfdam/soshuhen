package app.soshuhen

import android.app.Application
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.AndroidNetworkInfo
import app.soshuhen.core.AppGraph
import app.soshuhen.core.DataStoreServerStore
import app.soshuhen.core.ImportEnvironment
import app.soshuhen.core.ImportScheduler
import app.soshuhen.core.LocalStore
import app.soshuhen.core.Notifier
import app.soshuhen.core.SafChapterFolder
import app.soshuhen.db.databaseBuilder
import app.soshuhen.core.EpubCheck
import app.soshuhen.reader.ZipPages
import okio.Path.Companion.toPath
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn

class SoshuhenApplication : Application(), ImportEnvironment {
    // One per process: DataStore refuses two instances on the same file.
    override val graph: AppGraph by lazy {
        val database = databaseBuilder(this).build()
        val servers = DataStoreServerStore(this)
        val scope = MainScope()
        val zip = ZipPages(cacheDir.absolutePath.toPath())
        // Read once before anything asks: started at null, the folder said it
        // was unavailable for the moment DataStore took, and a worker or the
        // first-run check that asked then sent the user back to the picker.
        val picked = runBlocking { servers.folder.first() }
        AppGraph(
            servers,
            AndroidNetworkInfo(this),
            soshuhenHttpClient(),
            scope,
            LocalStore(database),
            SafChapterFolder(this, servers.folder.stateIn(scope, SharingStarted.Eagerly, picked)),
            cacheDir.absolutePath.toPath(),
            zip,
            zip,
            EpubCheck { false },
        )
    }

    val platform: AndroidPlatform by lazy { AndroidPlatform(this) }

    override val notifier: Notifier by lazy { Notifier(this, R.drawable.ic_notification) }

    override fun onCreate() {
        super.onCreate()
        // Channels before anything can post: a notification to a channel that
        // does not exist is dropped without a word.
        notifier.createChannels()
        ImportScheduler.schedule(this)
    }
}
