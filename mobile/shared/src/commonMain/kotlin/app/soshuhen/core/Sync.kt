package app.soshuhen.core

import app.soshuhen.api.OffloadRequest
import app.soshuhen.api.OffloadResult
import kotlinx.coroutines.flow.first

private const val NOT_HOME = "Not on the home network: syncing needs the server"

/**
 * Copy what is missing, then check the device against the server before the
 * user is asked whether to delete the server's copies.
 */
class Sync(
    private val importRun: suspend (onProgress: (Int, Int) -> Unit) -> ImportReport,
    private val store: LocalStore,
    private val folder: ChapterFolder,
    private val atHome: () -> Boolean,
    private val offload: suspend (OffloadRequest) -> OffloadResult,
) {
    /** [scope] null is every marked series; the import itself always covers them all. */
    suspend fun run(scope: Set<Long>?, onProgress: (Int, Int) -> Unit = { _, _ -> }): SyncReport {
        if (!atHome()) return SyncReport(0, emptyList(), emptyList(), emptyList(), NOT_HOME)
        // The importer's last-byte probe also fills an ETag an older import left out.
        val imported = importRun(onProgress)
        val ids = scope ?: store.markedIds().first()
        val details = ids.sorted().mapNotNull { store.detailSnapshot(it) }
        val chapters = details.flatMap { d -> d.chapters.mapNotNull { store.deviceChapter(it.id) } }.associateBy { it.chapterId }
        val volumes = details.flatMap { d -> d.volumes.mapNotNull { v -> v.id?.let { store.deviceVolume(it) } } }.associateBy { it.volumeId }
        val slugs = details.associate { it.series.id to it.series.slug }
        val actual = mutableMapOf<String, Long?>()
        for (c in chapters.values) actual[c.uri] = sizeOf(slugs[c.seriesId], c.fileName, c.uri)
        for (v in volumes.values) actual[v.uri] = sizeOf(slugs[v.seriesId], v.fileName, v.uri)
        return checkSync(details, DeviceState(chapters, volumes, actual)).copy(problem = imported.problem)
    }

    private suspend fun sizeOf(slug: String?, fileName: String, uri: String): Long? {
        if (slug == null || !folder.exists(uri)) return null
        return folder.size(slug, fileName)
    }

    suspend fun offload(report: SyncReport): OffloadResult {
        check(report.allVerified) { "only a fully verified report may delete from the server" }
        return offload(report.offloadRequest())
    }
}
