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
    private val importRun: suspend (scope: Set<Long>?, onStep: (SyncProgress) -> Unit) -> ImportReport,
    private val store: LocalStore,
    private val folder: ChapterFolder,
    private val atHome: () -> Boolean,
    private val offload: suspend (OffloadRequest) -> OffloadResult,
) {
    /** [scope] null is every marked series; otherwise only those are copied and checked. */
    suspend fun run(scope: Set<Long>?, onStep: (SyncProgress) -> Unit = {}): SyncReport {
        if (!atHome()) return SyncReport(0, emptyList(), emptyList(), emptyList(), NOT_HOME)
        // The importer's last-byte probe also fills an ETag an older import left out.
        val imported = importRun(scope, onStep)
        val ids = scope ?: store.markedIds().first()
        val details = ids.sorted().mapNotNull { store.detailSnapshot(it) }
        val chapters = details.flatMap { d -> d.chapters.mapNotNull { store.deviceChapter(it.id) } }.associateBy { it.chapterId }
        val volumes = details.flatMap { d -> d.volumes.mapNotNull { v -> v.id?.let { store.deviceVolume(it) } } }.associateBy { it.volumeId }
        val slugs = details.associate { it.series.id to it.series.slug }
        val actual = mutableMapOf<String, Long?>()
        // Each lookup is a folder listing through SAF, slow enough over a few
        // hundred files that the dialog has to say it is still working.
        val files = chapters.values.map { Triple(it.seriesId, it.fileName, it.uri) } +
            volumes.values.map { Triple(it.seriesId, it.fileName, it.uri) }
        onStep(SyncProgress.Verifying(0, files.size))
        for ((i, f) in files.withIndex()) {
            actual[f.third] = sizeOf(slugs[f.first], f.second, f.third)
            onStep(SyncProgress.Verifying(i + 1, files.size))
        }
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
