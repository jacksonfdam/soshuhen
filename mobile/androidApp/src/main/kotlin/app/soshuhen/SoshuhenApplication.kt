package app.soshuhen

import android.app.Application
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.AndroidNetworkInfo
import app.soshuhen.core.AppGraph
import app.soshuhen.core.DataStoreServerStore
import app.soshuhen.core.LocalStore
import app.soshuhen.core.SafChapterFolder
import app.soshuhen.db.databaseBuilder
import okio.Path.Companion.toPath
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn

class SoshuhenApplication : Application() {
    // One per process: DataStore refuses two instances on the same file.
    val graph: AppGraph by lazy {
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
        )
    }
}
