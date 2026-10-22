package app.soshuhen.core

import kotlinx.coroutines.flow.Flow

interface NetworkInfo {
    /** The device's IPv4 address and prefix length on Wi-Fi; null off Wi-Fi. */
    fun wifiAddress(): Pair<String, Int>?

    /**
     * Emits each time a default network becomes available or is lost. Android
     * reports the network the device is already on as soon as collection
     * starts, so with a network there is an emission at once; with none there
     * is nothing until one appears. A collector that must act at startup either
     * way does so itself.
     */
    val changes: Flow<Unit>
}
