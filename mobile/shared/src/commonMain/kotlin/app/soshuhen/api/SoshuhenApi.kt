package app.soshuhen.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.HttpTimeoutConfig
import io.ktor.client.plugins.timeout
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.prepareGet
import io.ktor.client.request.put
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsChannel
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlin.time.Instant

@Serializable
private data class PositionBody(
    @SerialName("chapter_id") val chapterId: Long,
    val page: Int,
    @SerialName("read_at") val readAt: String,
)

@Serializable
private data class CompleteBody(@SerialName("read_at") val readAt: String)

// No `custom`: the server's PrefsIn takes exactly these three.
@Serializable
private data class PrefsBody(val mode: String, val scale: String, val background: String)

class ApiException(val status: Int) : Exception("server answered $status")

/** The Soshuhen server, and nothing else: every URL here is built on [baseUrl]. */
class SoshuhenApi(val baseUrl: String, private val client: HttpClient) {

    suspend fun identity(): Identity = checked(client.get("$baseUrl/api/identity")).body()

    // The raw bodies exist so a snapshot stores exactly what the server said;
    // the typed calls decode the same text.
    suspend fun seriesJson(): String = checked(client.get("$baseUrl/api/series")).bodyAsText()

    suspend fun series(): List<Series> = SoshuhenJson.decodeFromString(seriesJson())

    suspend fun seriesDetailJson(id: Long): String =
        checked(client.get("$baseUrl/api/series/$id")).bodyAsText()

    suspend fun seriesDetail(id: Long): SeriesDetail = SoshuhenJson.decodeFromString(seriesDetailJson(id))

    suspend fun resume(seriesId: Long): Resume? {
        val response = client.get("$baseUrl/api/reader/series/$seriesId/resume")
        if (response.status == HttpStatusCode.NotFound) return null
        return checked(response).body()
    }

    // Never cover_url: that is the list provider's CDN, and the phone talks to
    // nothing outside the home network.
    fun coverUrl(seriesId: Long): String = "$baseUrl/api/series/$seriesId/cover"

    // read_at is UTC ISO-8601 so a replay from the train keeps when the reading happened.
    suspend fun putPosition(seriesId: Long, chapterId: Long, page: Int, readAt: Instant) {
        checked(
            client.put("$baseUrl/api/reader/series/$seriesId/position") {
                contentType(ContentType.Application.Json)
                setBody(PositionBody(chapterId, page, readAt.toString()))
            },
        )
    }

    suspend fun complete(chapterId: Long, readAt: Instant) {
        checked(
            client.post("$baseUrl/api/reader/chapters/$chapterId/complete") {
                contentType(ContentType.Application.Json)
                setBody(CompleteBody(readAt.toString()))
            },
        )
    }

    suspend fun prefs(seriesId: Long): ReaderPrefs =
        checked(client.get("$baseUrl/api/reader/series/$seriesId/prefs")).body()

    suspend fun putPrefs(seriesId: Long, prefs: ReaderPrefs) {
        checked(
            client.put("$baseUrl/api/reader/series/$seriesId/prefs") {
                contentType(ContentType.Application.Json)
                setBody(PrefsBody(prefs.mode, prefs.scale, prefs.background))
            },
        )
    }

    suspend fun manifest(chapterId: Long): Manifest =
        checked(client.get("$baseUrl/api/reader/chapters/$chapterId")).body()

    fun pageUrl(chapterId: Long, index: Int): String = "$baseUrl/api/reader/chapters/$chapterId/pages/$index"

    // prepareGet(...).execute streams: a chapter is tens of megabytes and the
    // phone must not hold one in memory. That is why the channel is only valid
    // inside [read].
    suspend fun <T> archive(chapterId: Long, from: Long, read: suspend (ArchiveDownload) -> T): T =
        client.prepareGet("$baseUrl/api/chapters/$chapterId/archive") {
            if (from > 0) header(HttpHeaders.Range, "bytes=$from-")
            // The default 15 s request timeout covers the whole body and would
            // cut off any copy over weak Wi-Fi; a stalled socket is what to detect.
            timeout {
                requestTimeoutMillis = HttpTimeoutConfig.INFINITE_TIMEOUT_MS
                socketTimeoutMillis = 30_000
            }
        }.execute { response ->
            checked(response)
            val total = response.headers[HttpHeaders.ContentRange]?.substringAfter('/')?.toLongOrNull()
                ?: response.headers[HttpHeaders.ContentLength]?.toLongOrNull()
            read(
                ArchiveDownload(
                    body = response.bodyAsChannel(),
                    etag = response.headers[HttpHeaders.ETag],
                    total = total,
                    restarted = from > 0 && response.status == HttpStatusCode.OK,
                ),
            )
        }

    private fun checked(response: HttpResponse): HttpResponse {
        if (!response.status.isSuccess()) throw ApiException(response.status.value)
        return response
    }
}
