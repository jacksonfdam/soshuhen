package app.soshuhen.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.statement.HttpResponse
import io.ktor.http.HttpStatusCode
import io.ktor.http.isSuccess

class ApiException(val status: Int) : Exception("server answered $status")

/** The Soshuhen server, and nothing else: every URL here is built on [baseUrl]. */
class SoshuhenApi(val baseUrl: String, private val client: HttpClient) {

    suspend fun identity(): Identity = checked(client.get("$baseUrl/api/identity")).body()

    suspend fun series(): List<Series> = checked(client.get("$baseUrl/api/series")).body()

    suspend fun seriesDetail(id: Long): SeriesDetail =
        checked(client.get("$baseUrl/api/series/$id")).body()

    suspend fun resume(seriesId: Long): Resume? {
        val response = client.get("$baseUrl/api/reader/series/$seriesId/resume")
        if (response.status == HttpStatusCode.NotFound) return null
        return checked(response).body()
    }

    // Never cover_url: that is the list provider's CDN, and the phone talks to
    // nothing outside the home network.
    fun coverUrl(seriesId: Long): String = "$baseUrl/api/series/$seriesId/cover"

    private fun checked(response: HttpResponse): HttpResponse {
        if (!response.status.isSuccess()) throw ApiException(response.status.value)
        return response
    }
}
