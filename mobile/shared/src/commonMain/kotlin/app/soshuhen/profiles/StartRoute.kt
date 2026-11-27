package app.soshuhen.profiles

import app.soshuhen.api.Profile
import app.soshuhen.api.key

/** Whether the app opens on the picker or straight into a profile's library. */
sealed interface StartRoute {
    /** Not yet known whether the phone is home, or whose data the session reads: show nothing. */
    data object Deciding : StartRoute
    data object Picker : StartRoute
    data class Open(val key: Long) : StartRoute
}

/**
 * Where a start lands.
 *
 * At home with more than one profile, every cold start asks: a tablet put down
 * by one person is picked up by another. Away from home the PIN cannot be
 * checked, so the last profile opens as it was left rather than locking the
 * owner out of their own offline reading. A saved profile the server no
 * longer lists was deleted, and asking again beats every request failing.
 */
fun startRoute(
    profiles: List<Profile>?,
    atHome: Boolean,
    saved: Long?,
    chosen: Boolean,
    switching: Boolean,
): StartRoute {
    if (switching) return StartRoute.Picker
    val last = saved ?: 0L
    if (profiles == null) return StartRoute.Open(last)
    if (profiles.size <= 1) return StartRoute.Open(0L)
    if (atHome && saved != null && profiles.none { it.key() == saved }) return StartRoute.Picker
    if (chosen || !atHome) return StartRoute.Open(last)
    return StartRoute.Picker
}
