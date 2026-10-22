package app.soshuhen.core

import okio.Buffer
import okio.ForwardingSource
import okio.Sink
import okio.Source

class FakeChapterFolder : ChapterFolder {
    val files = mutableMapOf<String, ByteArray>()
    var available = true
    var failDeleteWith: Exception? = null

    // Thrown after the bytes are stored, as a disk that fills mid-copy leaves
    // what it managed to write behind.
    var failNextWriteWith: Exception? = null

    // A card pulled mid-run: SAF then fails with whatever the provider throws,
    // not with FolderUnavailable.
    var goneWith: Exception? = null

    fun uri(slug: String, name: String) = "mem://Soshuhen/$slug/$name"

    override fun isAvailable() = available && goneWith == null

    private fun gone() = goneWith?.let { throw it }

    override suspend fun write(slug: String, fileName: String, append: Boolean, block: suspend (Sink) -> Unit) {
        gone()
        if (!available) throw FolderUnavailable()
        val buffer = Buffer()
        block(buffer)
        val key = uri(slug, fileName)
        files[key] = (if (append) files[key] ?: ByteArray(0) else ByteArray(0)) + buffer.readByteArray()
        failNextWriteWith?.let {
            failNextWriteWith = null
            throw it
        }
    }

    override suspend fun size(slug: String, fileName: String): Long? {
        gone()
        if (!available) throw FolderUnavailable()
        return files[uri(slug, fileName)]?.size?.toLong()
    }

    override suspend fun find(slug: String, fileName: String): String? {
        gone()
        if (!available) throw FolderUnavailable()
        return uri(slug, fileName).takeIf { it in files }
    }

    override suspend fun rename(slug: String, from: String, to: String): String {
        gone()
        val bytes = files.remove(uri(slug, from)) ?: throw ChapterFileMissing()
        files[uri(slug, to)] = bytes
        return uri(slug, to)
    }

    override suspend fun delete(uri: String) {
        failDeleteWith?.let { throw it }
        files.remove(uri) ?: throw ChapterFileMissing()
    }

    override suspend fun exists(uri: String) = uri in files

    // Every source handed out, so a test can see that each one was closed:
    // on Android each is an open file descriptor.
    val opened = mutableListOf<ClosingSource>()

    class ClosingSource(delegate: Source) : ForwardingSource(delegate) {
        var closed = false
        override fun close() {
            closed = true
            super.close()
        }
    }

    override suspend fun read(uri: String): Source =
        ClosingSource(Buffer().write(files[uri] ?: throw ChapterFileMissing())).also { opened += it }

    fun put(slug: String, name: String): String = uri(slug, name).also { files[it] = byteArrayOf(1, 2, 3) }
}
