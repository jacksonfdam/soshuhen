package app.soshuhen.core

import okio.Buffer
import okio.Sink
import okio.Source

class FakeChapterFolder : ChapterFolder {
    val files = mutableMapOf<String, ByteArray>()
    var available = true
    var failDeleteWith: Exception? = null

    private fun uri(slug: String, name: String) = "mem://Soshuhen/$slug/$name"

    override fun isAvailable() = available

    override suspend fun write(slug: String, fileName: String, append: Boolean, block: suspend (Sink) -> Unit) {
        if (!available) throw FolderUnavailable()
        val buffer = Buffer()
        block(buffer)
        val key = uri(slug, fileName)
        files[key] = (if (append) files[key] ?: ByteArray(0) else ByteArray(0)) + buffer.readByteArray()
    }

    override suspend fun size(slug: String, fileName: String): Long? = files[uri(slug, fileName)]?.size?.toLong()

    override suspend fun rename(slug: String, from: String, to: String): String {
        val bytes = files.remove(uri(slug, from)) ?: throw ChapterFileMissing()
        files[uri(slug, to)] = bytes
        return uri(slug, to)
    }

    override suspend fun delete(uri: String) {
        failDeleteWith?.let { throw it }
        files.remove(uri) ?: throw ChapterFileMissing()
    }

    override suspend fun exists(uri: String) = uri in files

    override suspend fun read(uri: String): Source = Buffer().write(files[uri] ?: throw ChapterFileMissing())

    fun put(slug: String, name: String): String = uri(slug, name).also { files[it] = byteArrayOf(1, 2, 3) }
}
