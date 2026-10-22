package app.soshuhen.server

data class ServerAddress(val scheme: String, val host: String, val port: Int) {
    val baseUrl: String get() = "$scheme://$host:$port"
}

data class SavedServer(val address: ServerAddress, val instanceId: String)

private val HOST = Regex("[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?")

/**
 * What a person typed into the address field, or null when it is not an
 * address. 8080 is the port `web` publishes, so a bare IP means that.
 */
fun parseServerAddress(input: String): ServerAddress? {
    var rest = input.trim()
    var scheme = "http"
    val separator = rest.indexOf("://")
    if (separator >= 0) {
        scheme = rest.substring(0, separator).lowercase()
        if (scheme != "http" && scheme != "https") return null
        rest = rest.substring(separator + 3).removeSuffix("/")
        // The app adds /api itself; a path typed here would be doubled.
        if ('/' in rest) return null
    }
    val host = rest.substringBefore(':')
    if (!HOST.matches(host)) return null
    val port = if (':' in rest) {
        rest.substringAfter(':').toIntOrNull()?.takeIf { it in 1..65535 } ?: return null
    } else if (scheme == "https") 443 else 8080
    return ServerAddress(scheme, host, port)
}
