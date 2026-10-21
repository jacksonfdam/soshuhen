package app.soshuhen.core

interface NetworkInfo {
    /** The device's IPv4 address and prefix length on Wi-Fi; null off Wi-Fi. */
    fun wifiAddress(): Pair<String, Int>?
}
