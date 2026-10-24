package app.soshuhen.reader

import app.soshuhen.api.SoshuhenJson
import app.soshuhen.core.BookRef
import app.soshuhen.core.LocalStore
import kotlinx.serialization.Serializable
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.serializer

/** How every novel on this device is set: the reader's choice, not the book's. */
@Serializable
data class ProseStyle(val fontSize: Int = 18, val font: String = "serif", val background: String = "black")

val PROSE_FONTS = listOf("serif" to "Serif", "sans" to "Sans", "app" to "Jakarta")
val PROSE_BACKGROUNDS = listOf("black" to "Black", "gray" to "Gray", "white" to "White", "sepia" to "Sepia")
val PROSE_SIZES = 14..28 step 2
const val DEFAULT_PROSE_MODE = "paged_ltr"

/**
 * The prose reader's own state, on the device only: the server's reader
 * prefs belong to the web's reader, and a place in a book is not a page it
 * could store.
 */
class ProseStore(private val local: LocalStore) {
    suspend fun position(ref: BookRef): ProsePosition? = read("prose/${ref.kind.key}/${ref.id}", ProsePosition.serializer())

    suspend fun savePosition(ref: BookRef, p: ProsePosition) =
        local.putValue("prose/${ref.kind.key}/${ref.id}", SoshuhenJson.encodeToString(ProsePosition.serializer(), p))

    suspend fun style(): ProseStyle = read(STYLE, ProseStyle.serializer()) ?: ProseStyle()

    suspend fun saveStyle(style: ProseStyle) = local.putValue(STYLE, SoshuhenJson.encodeToString(ProseStyle.serializer(), style))

    suspend fun mode(seriesId: Long): String? = local.value("prose-mode/$seriesId")?.let {
        decode(it, String.serializer())
    }

    suspend fun saveMode(seriesId: Long, mode: String) =
        local.putValue("prose-mode/$seriesId", SoshuhenJson.encodeToString(String.serializer(), mode))

    private suspend fun <T> read(key: String, serializer: KSerializer<T>): T? =
        local.value(key)?.let { decode(it, serializer) }

    // A value the current shape cannot read is no value: the reader falls back to its default.
    private fun <T> decode(json: String, serializer: KSerializer<T>): T? = try {
        SoshuhenJson.decodeFromString(serializer, json)
    } catch (_: SerializationException) {
        null
    }

    private companion object {
        const val STYLE = "prose-style"
    }
}
