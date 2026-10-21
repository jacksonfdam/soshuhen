package app.soshuhen.core

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

private const val PERIODIC = "import-periodic"
private const val NOW = "import-now"

object ImportScheduler {
    // The worker needs the home network, and Android cannot ask for "the Wi-Fi
    // with this server on it": any connection wakes it and the run itself
    // decides, from the saved instance id, whether it is home.
    private val constraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresBatteryNotLow(true)
        .build()

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<ImportWorker>(1, TimeUnit.HOURS)
            .setConstraints(constraints)
            .build()
        // KEEP: a later app start must not push back a run already counting down.
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request)
    }

    fun runNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<ImportWorker>().setConstraints(constraints).build()
        // KEEP: a second pull-to-refresh while a copy is running must not
        // queue a second copy of the same chapters behind it.
        WorkManager.getInstance(context)
            .enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, request)
    }
}
