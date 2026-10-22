package app.soshuhen.ui

/**
 * The app's equivalent of the web's lib/useAsyncData.ts. A request that has
 * not landed, a first load that failed, and a refresh that failed over loaded
 * data are three different things to show; built one screen at a time on the
 * web, they did not look different, and the same would happen here.
 */
sealed interface LoadState<out T> {
    data object Loading : LoadState<Nothing>
    data class Loaded<T>(val data: T, val refreshFailed: String? = null) : LoadState<T>
    data class Failed(val message: String) : LoadState<Nothing>
}

const val UNREACHABLE = "Can't reach the server. Showing what was loaded."
const val OFFLINE = "Offline. Showing the last sync."
const val FAILED_FIRST = "Can't reach the server."

/**
 * Saving a snapshot is a courtesy to the next offline start. If it fails, what
 * the server just said is still the truth to show, not an "offline" copy.
 */
suspend inline fun keep(save: suspend () -> Unit) {
    try {
        save()
    } catch (e: kotlinx.coroutines.CancellationException) {
        throw e
    } catch (_: Exception) {
    }
}
