package app.soshuhen.core

import kotlinx.coroutines.flow.Flow

interface NetworkInfo {
    /** The device's IPv4 address and prefix length on Wi-Fi; null off Wi-Fi. */
    fun wifiAddress(): Pair<String, Int>?

    /**
     * Emits once on collection and again each time the device's default network
     * changes, so the session looks for the server at startup and on every move
     * without a second, separate initial check.
     */
    val changes: Flow<Unit>
}
