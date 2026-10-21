package app.soshuhen.core

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.documentfile.provider.DocumentFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.withContext
import okio.Sink
import okio.Source
import okio.sink
import okio.source
import okio.buffer
import java.io.FileNotFoundException
import java.io.IOException

private const val ROOT = "Soshuhen"
private const val BINARY = "application/octet-stream"

/**
 * The picked folder through the Storage Access Framework: the only way to
 * write to a folder of the user's choosing without broad storage access.
 */
class SafChapterFolder(
    private val context: Context,
    private val treeUri: StateFlow<String?>,
) : ChapterFolder {
    private val resolver get() = context.contentResolver

    private fun tree(): DocumentFile {
        val uri = treeUri.value ?: throw FolderUnavailable("No folder picked")
        return DocumentFile.fromTreeUri(context, Uri.parse(uri))?.takeIf { it.exists() && it.canWrite() }
            ?: throw FolderUnavailable("The folder is gone")
    }

    override fun isAvailable(): Boolean {
        val uri = treeUri.value ?: return false
        val granted = resolver.persistedUriPermissions.any {
            it.uri == Uri.parse(uri) && it.isReadPermission && it.isWritePermission
        }
        return granted && DocumentFile.fromTreeUri(context, Uri.parse(uri))?.exists() == true
    }

    private fun child(parent: DocumentFile, name: String, create: Boolean): DocumentFile? =
        parent.findFile(name)?.takeIf { it.isDirectory }
            ?: if (create) parent.createDirectory(name) ?: throw FolderUnavailable("Cannot create $name") else null

    private fun seriesDir(slug: String, create: Boolean): DocumentFile? {
        val root = child(tree(), ROOT, create) ?: return null
        return child(root, slug, create)
    }

    // SAF reports a full disk only as an IOException with the errno's text.
    private inline fun <T> mapIo(block: () -> T): T = try {
        block()
    } catch (e: FileNotFoundException) {
        throw ChapterFileMissing()
    } catch (e: IOException) {
        if (e.message?.contains("ENOSPC") == true || e.message?.contains("No space left on device") == true) throw DeviceFull()
        throw e
    } catch (e: SecurityException) {
        throw FolderUnavailable(e.message)
    }

    override suspend fun write(slug: String, fileName: String, append: Boolean, block: suspend (Sink) -> Unit) {
        val file = withContext(Dispatchers.IO) {
            val dir = seriesDir(slug, create = true)!!
            dir.findFile(fileName) ?: createNamed(dir, fileName)
        }
        val out = withContext(Dispatchers.IO) {
            mapIo { resolver.openOutputStream(file.uri, if (append) "wa" else "w") } ?: throw FolderUnavailable("Cannot open $fileName")
        }
        withContext(Dispatchers.IO) { mapIo { out.sink().buffer().use { block(it) } } }
    }

    // A provider may append an extension to the type it was given or otherwise
    // alter the display name. Later steps address the file by the exact server
    // name, and the .part to final rename depends on it, so name it again.
    private fun createNamed(dir: DocumentFile, fileName: String): DocumentFile {
        val created = dir.createFile(BINARY, fileName) ?: throw FolderUnavailable("Cannot create $fileName")
        if (created.name == fileName) return created
        val renamed = DocumentsContract.renameDocument(resolver, created.uri, fileName)
            ?: throw FolderUnavailable("Cannot name $fileName")
        return DocumentFile.fromSingleUri(context, renamed) ?: throw FolderUnavailable("Cannot name $fileName")
    }

    override suspend fun size(slug: String, fileName: String): Long? = withContext(Dispatchers.IO) {
        seriesDir(slug, create = false)?.findFile(fileName)?.length()
    }

    override suspend fun rename(slug: String, from: String, to: String): String = withContext(Dispatchers.IO) {
        val dir = seriesDir(slug, create = false) ?: throw ChapterFileMissing()
        val file = dir.findFile(from) ?: throw ChapterFileMissing()
        dir.findFile(to)?.delete()
        DocumentsContract.renameDocument(resolver, file.uri, to)?.toString() ?: throw FolderUnavailable("Cannot rename $from")
    }

    override suspend fun delete(uri: String) {
        withContext(Dispatchers.IO) {
            // exists() swallows the SecurityException of a revoked permission and
            // answers false, which would read as a file already gone and make the
            // index forget one that is still on disk.
            tree()
            val file = DocumentFile.fromSingleUri(context, Uri.parse(uri))
            if (file == null || !file.exists()) throw ChapterFileMissing()
            if (!file.delete()) throw FolderUnavailable("Cannot delete")
        }
    }

    override suspend fun exists(uri: String): Boolean = withContext(Dispatchers.IO) {
        tree()
        DocumentFile.fromSingleUri(context, Uri.parse(uri))?.exists() == true
    }

    override suspend fun read(uri: String): Source = withContext(Dispatchers.IO) {
        mapIo { resolver.openInputStream(Uri.parse(uri)) }?.source() ?: throw ChapterFileMissing()
    }
}
