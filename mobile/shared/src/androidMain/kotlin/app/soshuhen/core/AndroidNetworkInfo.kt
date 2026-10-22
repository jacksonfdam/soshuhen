package app.soshuhen.core

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import java.net.Inet4Address

class AndroidNetworkInfo(context: Context) : NetworkInfo {
    private val connectivity = context.getSystemService(ConnectivityManager::class.java)

    override val changes: Flow<Unit> = callbackFlow {
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { trySend(Unit) }
            override fun onLost(network: Network) { trySend(Unit) }
        }
        connectivity.registerDefaultNetworkCallback(callback)
        awaitClose { connectivity.unregisterNetworkCallback(callback) }
    }

    override fun wifiAddress(): Pair<String, Int>? {
        val network = connectivity.activeNetwork ?: return null
        val capabilities = connectivity.getNetworkCapabilities(network) ?: return null
        // Ethernet too: a tablet on a USB dock is on the same home network.
        val local = capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
        if (!local) return null
        val link = connectivity.getLinkProperties(network) ?: return null
        val v4 = link.linkAddresses.firstOrNull { it.address is Inet4Address } ?: return null
        return v4.address.hostAddress!! to v4.prefixLength
    }
}
