package app.soshuhen.core

import android.content.Context
import android.content.pm.ServiceInfo
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.launch

// Below this a run is over before a notification would be read.
private const val LONG_RUN = 5

class ImportWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val env = applicationContext as? ImportEnvironment ?: return Result.failure()
        val notifier = env.notifier
        return try {
            val report = coroutineScope {
                val progress = MutableStateFlow<Pair<Int, Int>?>(null)
                var long = false
                val watcher = launch {
                    var foreground = false
                    progress.filterNotNull().collect { (done, total) ->
                        if (!long) return@collect
                        if (!foreground) {
                            foreground = promote(notifier, done, total)
                            // Refused: the run goes on without one, silently.
                            if (!foreground) long = false
                        } else {
                            notifier.updateProgress(done, total)
                        }
                    }
                }
                try {
                    env.graph.importer.run(
                        onPlan = { missing -> long = missing > LONG_RUN },
                        onProgress = { done, total -> progress.value = done to total },
                    )
                } finally {
                    watcher.cancel()
                }
            }
            notifier.newChapters(report)
            Result.success()
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            // failure(), never retry(): a one-time request waiting out backoff
            // stays ENQUEUED for hours, and ExistingWorkPolicy.KEEP would then
            // ignore every later runNow. A periodic one keeps its schedule.
            // run() already records folder and network trouble as the problem
            // banner, which this must not touch.
            Result.failure()
        }
    }

    private suspend fun promote(notifier: Notifier, done: Int, total: Int): Boolean = try {
        setForeground(
            ForegroundInfo(
                notifier.progressId,
                notifier.progress(done, total),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            ),
        )
        true
    } catch (_: IllegalStateException) {
        // ForegroundServiceStartNotAllowedException is one: started from the
        // background, where the system forbids a foreground service. The copy
        // is still worth doing without one.
        false
    }
}
