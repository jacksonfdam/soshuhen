package app.soshuhen

import android.app.Application
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.core.AndroidNetworkInfo
import app.soshuhen.core.AppGraph
import app.soshuhen.core.DataStoreServerStore
import kotlinx.coroutines.MainScope

class SoshuhenApplication : Application() {
    // One per process: DataStore refuses two instances on the same file.
    val graph: AppGraph by lazy {
        AppGraph(DataStoreServerStore(this), AndroidNetworkInfo(this), soshuhenHttpClient(), MainScope())
    }
}
