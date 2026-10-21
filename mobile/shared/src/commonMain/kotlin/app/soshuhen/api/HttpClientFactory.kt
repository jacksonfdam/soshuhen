package app.soshuhen.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

val SoshuhenJson = Json {
    ignoreUnknownKeys = true
    // A null where the model has a default (downloaded, progress) takes the
    // default instead of failing the whole library.
    coerceInputValues = true
    explicitNulls = false
}

fun soshuhenHttpClient(engine: HttpClientEngine? = null): HttpClient {
    val configure: io.ktor.client.HttpClientConfig<*>.() -> Unit = {
        install(ContentNegotiation) { json(SoshuhenJson) }
        install(HttpTimeout) {
            // The server is on the same LAN: a connection that has not opened
            // in three seconds is not going to.
            connectTimeoutMillis = 3_000
            requestTimeoutMillis = 15_000
        }
        expectSuccess = false
        // The API never redirects. Something else on the LAN answering a scan
        // probe (a router, a captive portal) would, and following it would
        // send the phone to a host off the home network.
        followRedirects = false
    }
    return if (engine != null) HttpClient(engine, configure) else HttpClient(configure)
}
