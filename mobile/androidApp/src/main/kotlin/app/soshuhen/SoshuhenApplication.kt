package app.soshuhen

import android.app.Application
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.AndroidNetworkInfo
import app.soshuhen.core.AppGraph
import app.soshuhen.core.DataStoreServerStore
import app.soshuhen.core.LocalStore
import app.soshuhen.db.databaseBuilder
import okio.Path.Companion.toPath
import kotlinx.coroutines.MainScope

class SoshuhenApplication : Application() {
    // One per process: DataStore refuses two instances on the same file.
    val graph: AppGraph by lazy {
        val database = databaseBuilder(this).build()
        AppGraph(
            DataStoreServerStore(this),
            AndroidNetworkInfo(this),
            soshuhenHttpClient(),
            MainScope(),
            LocalStore(database),
            cacheDir.absolutePath.toPath(),
        )
    }
}
