package app.soshuhen.core

/**
 * What a sync is doing right now, step by step. A bare "Copying 105 of 385"
 * said neither what was being copied nor, while the series were still being
 * read from the server, that anything was happening at all.
 */
sealed interface SyncProgress {
    data object Starting : SyncProgress

    /** [done] series of [total] read from the server so far. */
    data class Reading(val done: Int, val total: Int) : SyncProgress

    /** On item [done] (zero-based) of [total]; [copying] is false while only checking it is current. */
    data class Item(
        val done: Int,
        val total: Int,
        val copied: Int,
        val title: String,
        val kind: BookKind,
        val number: Double,
        val copying: Boolean,
    ) : SyncProgress

    /** [done] of [total] files on this device checked against the index. */
    data class Verifying(val done: Int, val total: Int) : SyncProgress
}

fun progressText(p: SyncProgress): String = when (p) {
    SyncProgress.Starting -> "Checking what the server holds…"
    is SyncProgress.Reading -> "Reading series ${(p.done + 1).coerceAtMost(p.total)} of ${p.total} from the server…"
    is SyncProgress.Item -> {
        val label = if (p.kind == BookKind.Volume) "Vol." else "Ch."
        val verb = if (p.copying) "Copying" else "Checking"
        "${p.done + 1} of ${p.total} · ${p.copied} copied\n$verb ${p.title} · $label ${formatChapter(p.number)}"
    }
    is SyncProgress.Verifying -> "Checking files on this device: ${(p.done + 1).coerceAtMost(p.total)} of ${p.total}…"
}
