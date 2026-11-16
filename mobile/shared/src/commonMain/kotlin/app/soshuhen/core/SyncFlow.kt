package app.soshuhen.core

import app.soshuhen.api.OffloadResult
import app.soshuhen.ui.formatBytes
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Where a sync stands, for the dialog Settings and a series' screen share. */
sealed interface SyncUi {
    data object Idle : SyncUi
    data class Running(val done: Int, val total: Int) : SyncUi
    data class Ask(val report: SyncReport) : SyncUi
    data class Unverified(val report: SyncReport) : SyncUi
    data object Removing : SyncUi
    data class Done(val queued: Int) : SyncUi
    data class Failed(val message: String) : SyncUi
}

fun question(report: SyncReport): String =
    "All ${report.held.size} chapters of ${report.seriesCount} series are on this device. " +
        "Free ${formatBytes(report.bytes)} on the server?"

fun summary(report: SyncReport): String =
    "${report.held.size} of ${report.total} on device · ${report.missing.size} could not be copied"

private val REASON = mapOf(
    MissingReason.NotCopied to "not copied yet",
    MissingReason.FileGone to "file removed from this device",
    MissingReason.SizeMismatch to "file on this device has changed",
    MissingReason.NoEtag to "copied by an older version; copy it again",
    MissingReason.Unreadable to "file on this device cannot be opened",
)

/** Each reason once, with how many items it covers. */
fun reasons(report: SyncReport): List<String> =
    report.missing.groupingBy { it.reason }.eachCount().map { (reason, n) -> "$n ${REASON.getValue(reason)}" }

/**
 * Sync, then the question. Keep is the default: dismissing the dialog sends
 * nothing, and deleting is only reachable from a fully verified report.
 */
class SyncFlow(
    private val run: suspend (onProgress: (Int, Int) -> Unit) -> SyncReport,
    private val offload: suspend (SyncReport) -> OffloadResult,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow<SyncUi>(SyncUi.Idle)
    val state: StateFlow<SyncUi> = _state

    fun start() {
        if (_state.value is SyncUi.Running || _state.value == SyncUi.Removing) return
        _state.value = SyncUi.Running(0, 0)
        scope.launch {
            _state.value = try {
                val report = run { done, total -> _state.value = SyncUi.Running(done, total) }
                when {
                    report.problem != null -> SyncUi.Failed(report.problem)
                    report.allVerified -> SyncUi.Ask(report)
                    else -> SyncUi.Unverified(report)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                SyncUi.Failed(e.message ?: "Sync failed")
            }
        }
    }

    fun keep() {
        _state.value = SyncUi.Idle
    }

    fun deleteFromServer() {
        val report = (_state.value as? SyncUi.Ask)?.report ?: return
        _state.value = SyncUi.Removing
        scope.launch {
            _state.value = try {
                SyncUi.Done(offload(report).queued)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                SyncUi.Failed(e.message ?: "The server did not accept it")
            }
        }
    }
}
