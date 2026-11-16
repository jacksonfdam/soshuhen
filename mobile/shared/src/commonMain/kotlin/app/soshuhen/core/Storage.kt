package app.soshuhen.core

data class VolumeSpace(val free: Long, val total: Long)

/**
 * The filesystem root of the volume a SAF tree URI points into: the phone's own
 * storage for "primary", a card's mount by its id otherwise. Only the volume is
 * read from it, never a file, so a statfs on it needs no storage permission.
 */
fun storageRoot(treeUri: String): String? {
    val encoded = treeUri.substringAfterLast("/tree/", missingDelimiterValue = "")
    if (encoded.isEmpty()) return null
    val volume = percentDecode(encoded.substringBefore('/')).substringBefore(':', missingDelimiterValue = "")
    return when {
        volume.isEmpty() -> null
        volume == "primary" -> "/storage/emulated/0"
        volume.contains('/') || volume.contains("..") -> null
        else -> "/storage/$volume"
    }
}

internal fun percentDecode(s: String): String {
    val bytes = mutableListOf<Byte>()
    var i = 0
    while (i < s.length) {
        val c = s[i]
        val escaped = if (c == '%' && i + 2 < s.length) s.substring(i + 1, i + 3).toIntOrNull(16) else null
        if (escaped != null) {
            bytes += escaped.toByte()
            i += 3
        } else {
            bytes += c.toString().encodeToByteArray().toList()
            i++
        }
    }
    return bytes.toByteArray().decodeToString()
}
