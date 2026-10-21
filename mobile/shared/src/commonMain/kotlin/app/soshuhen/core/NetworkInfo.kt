package app.soshuhen.core

import kotlinx.coroutines.flow.Flow

interface NetworkInfo {
    /** The device's IPv4 address and prefix length on Wi-Fi; null off Wi-Fi. */
    fun wifiAddress(): Pair<String, Int>?

    /** Emits each time the device's default network changes, so the session can look for the server again. */
    val changes: Flow<Unit>
}
