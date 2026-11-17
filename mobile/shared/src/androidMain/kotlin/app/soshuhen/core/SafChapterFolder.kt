package app.soshuhen.core

import android.content.Context
import android.net.Uri
import android.os.Environment
import android.os.StatFs
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
            ?: if (create) parent.createDirectory(name) ?: throw refused(name) else null

    private fun refused(name: String): Exception = refusedToCreate(isAvailable(), freeBytes(), name)

    // The volume's own figure, read where it is mounted. Asking the documents
    // provider for its roots would be simpler, but needs a permission only the
    // system holds. A tree id is "<volume>:<path>", "primary" for internal storage.
    private fun freeBytes(): Long? = try {
        val tree = Uri.parse(treeUri.value ?: return null)
        val volume = DocumentsContract.getTreeDocumentId(tree).substringBefore(':')
        val mount = when {
            volume == "primary" -> Environment.getExternalStorageDirectory().path
            volume.isEmpty() || volume.contains('/') || volume.contains("..") -> return null
            else -> "/storage/$volume"
        }
        StatFs(mount).availableBytes
    } catch (_: Exception) {
        null
    }

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
            mapIo { resolver.openOutputStream(file.uri, writeMode(append)) } ?: throw FolderUnavailable("Cannot open $fileName")
        }
        withContext(Dispatchers.IO) { mapIo { out.sink().buffer().use { block(it) } } }
    }

    // A provider may append an extension to the type it was given or otherwise
    // alter the display name. Later steps address the file by the exact server
    // name, and the .part to final rename depends on it, so name it again.
    private fun createNamed(dir: DocumentFile, fileName: String): DocumentFile {
        val created = dir.createFile(BINARY, fileName) ?: throw refused(fileName)
        if (created.name == fileName) return created
        val renamed = DocumentsContract.renameDocument(resolver, created.uri, fileName)
            ?: throw FolderUnavailable("Cannot name $fileName")
        return DocumentFile.fromSingleUri(context, renamed) ?: throw FolderUnavailable("Cannot name $fileName")
    }

    override suspend fun size(slug: String, fileName: String): Long? = withContext(Dispatchers.IO) {
        seriesDir(slug, create = false)?.findFile(fileName)?.length()
    }

    override suspend fun find(slug: String, fileName: String): String? = withContext(Dispatchers.IO) {
        seriesDir(slug, create = false)?.findFile(fileName)?.uri?.toString()
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

    // One listing per folder through the provider, reading each child's size
    // from the same query. DocumentFile would ask again for every file, which
    // over a few thousand chapters on a card takes minutes.
    override suspend fun usage(): Map<String, Long> = withContext(Dispatchers.IO) {
        val tree = Uri.parse(treeUri.value ?: return@withContext emptyMap())
        val root = child(tree(), ROOT, create = false) ?: return@withContext emptyMap()
        children(tree, DocumentsContract.getDocumentId(root.uri))
            .filter { it.isDir }
            .associate { dir -> dir.name to children(tree, dir.id).filterNot { it.isDir }.sumOf { it.size } }
    }

    private class Child(val id: String, val name: String, val isDir: Boolean, val size: Long)

    private fun children(tree: Uri, parentId: String): List<Child> {
        val uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parentId)
        val columns = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
        )
        return resolver.query(uri, columns, null, null, null)?.use { rows ->
            buildList {
                while (rows.moveToNext()) {
                    val isDir = rows.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR
                    add(Child(rows.getString(0), rows.getString(1), isDir, if (rows.isNull(3)) 0L else rows.getLong(3)))
                }
            }
        }.orEmpty()
    }

    override suspend fun exists(uri: String): Boolean = withContext(Dispatchers.IO) {
        tree()
        DocumentFile.fromSingleUri(context, Uri.parse(uri))?.exists() == true
    }

    override suspend fun read(uri: String): Source = withContext(Dispatchers.IO) {
        mapIo { resolver.openInputStream(Uri.parse(uri)) }?.source() ?: throw ChapterFileMissing()
    }
}
