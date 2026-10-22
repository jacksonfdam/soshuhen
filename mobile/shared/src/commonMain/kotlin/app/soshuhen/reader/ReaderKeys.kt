package app.soshuhen.reader

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

enum class ReaderKey { Next, Previous }

/**
 * Volume keys, from the activity to whichever reader is in front. The
 * activity emits only while a reader is showing, and [emit] says whether one
 * took the key, so the volume still changes everywhere else.
 */
object ReaderKeys {
    // A buffer so a key pressed while the collector is busy turning the
    // previous page is queued rather than reported as unconsumed.
    private val keys = MutableSharedFlow<ReaderKey>(extraBufferCapacity = 8)
    val events: SharedFlow<ReaderKey> = keys

    fun emit(k: ReaderKey): Boolean = keys.subscriptionCount.value > 0 && keys.tryEmit(k)
}

/** Volume down reads on, as on most e-readers; [inverted] is for a hand that prefers the other way. */
fun volumeKey(down: Boolean, inverted: Boolean): ReaderKey = if (down != inverted) ReaderKey.Next else ReaderKey.Previous
