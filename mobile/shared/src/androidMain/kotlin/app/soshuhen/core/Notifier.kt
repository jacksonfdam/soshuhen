package app.soshuhen.core

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat

const val NEW_CHAPTERS = "new_chapters"
const val IMPORT_PROGRESS = "import_progress"

/** The intent extra a notification carries so a tap can open its series. */
const val EXTRA_SERIES_ID = "series_id"

private const val SUMMARY_ID = 1
private const val PROGRESS_ID = 2
private const val GROUP = "new_chapters_group"

/**
 * The app's only two notifications: what was copied, and that a long copy is
 * under way. A failure raises neither; it waits in the problem banner.
 */
class Notifier(private val context: Context, private val smallIcon: Int) {
    private val manager get() = context.getSystemService(NotificationManager::class.java)

    fun createChannels() {
        manager.createNotificationChannel(
            NotificationChannel(NEW_CHAPTERS, "New chapters", NotificationManager.IMPORTANCE_DEFAULT),
        )
        manager.createNotificationChannel(
            NotificationChannel(IMPORT_PROGRESS, "Copying chapters", NotificationManager.IMPORTANCE_LOW),
        )
    }

    val progressId get() = PROGRESS_ID

    fun progress(done: Int, total: Int): Notification =
        NotificationCompat.Builder(context, IMPORT_PROGRESS)
            .setSmallIcon(smallIcon)
            .setContentTitle("Copying chapters")
            .setContentText("$done of $total")
            .setProgress(total, done, false)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()

    // Without the permission the call is dropped by the system; the Updates tab still lists the chapters.
    @SuppressLint("MissingPermission")
    fun updateProgress(done: Int, total: Int) = manager.notify(PROGRESS_ID, progress(done, total))

    @SuppressLint("MissingPermission")
    fun newChapters(report: ImportReport) {
        if (report.imported.isEmpty()) return
        for ((seriesId, numbers) in report.imported) {
            val (title, text) = newChaptersText(report.seriesTitles.getValue(seriesId), numbers)
            val notification = NotificationCompat.Builder(context, NEW_CHAPTERS)
                .setSmallIcon(smallIcon)
                .setContentTitle(title)
                .setContentText(text)
                .setContentIntent(open(seriesId))
                .setAutoCancel(true)
                .setGroup(GROUP)
                .build()
            // The series id doubles as the notification id, so a later run
            // about the same series replaces it rather than stacking.
            manager.notify(NOTIFICATION_BASE + seriesId.toInt(), notification)
        }
        if (report.imported.size > 1) {
            val summary = NotificationCompat.Builder(context, NEW_CHAPTERS)
                .setSmallIcon(smallIcon)
                .setContentTitle("New chapters")
                .setContentText("${report.imported.size} series have new chapters")
                .setGroup(GROUP)
                .setGroupSummary(true)
                .setAutoCancel(true)
                .build()
            manager.notify(SUMMARY_ID, summary)
        }
    }

    private fun open(seriesId: Long): PendingIntent {
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)!!
            .putExtra(EXTRA_SERIES_ID, seriesId)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        // The request code is the series id: a PendingIntent with the same
        // code and different extras would otherwise be reused and open the wrong series.
        return PendingIntent.getActivity(
            context, seriesId.toInt(), launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private companion object {
        const val NOTIFICATION_BASE = 1000
    }
}
