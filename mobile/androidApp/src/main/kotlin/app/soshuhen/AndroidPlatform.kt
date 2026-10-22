package app.soshuhen

import android.Manifest
import android.annotation.SuppressLint
import android.app.Application
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import app.soshuhen.core.Platform
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * One per process, so a view model that outlives a rotation still reaches the
 * activity that is on screen now. Each activity attaches its own launchers;
 * an answer that lands after a recreation completes the request made before it.
 */
class AndroidPlatform(private val app: Application) : Platform {
    private var activity: ComponentActivity? = null
    private var folderLauncher: ActivityResultLauncher<Uri?>? = null
    private var notificationLauncher: ActivityResultLauncher<String>? = null
    private var pendingFolder: CompletableDeferred<String?>? = null
    private var pendingNotifications: CompletableDeferred<Boolean>? = null

    /** Called from the activity's onCreate: results can only be registered before it starts. */
    fun attach(activity: ComponentActivity) {
        this.activity = activity
        folderLauncher = activity.registerForActivityResult(PersistableTree()) { uri -> finishPick(uri) }
        notificationLauncher = activity.registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            pendingNotifications?.complete(granted)
            pendingNotifications = null
        }
        activity.lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onDestroy(owner: LifecycleOwner) {
                if (this@AndroidPlatform.activity === activity) {
                    this@AndroidPlatform.activity = null
                    folderLauncher = null
                    notificationLauncher = null
                }
            }
        })
    }

    private fun finishPick(uri: Uri?) {
        val kept = uri?.let {
            try {
                // Without this the grant ends with the process, and the hourly
                // copy would find the folder gone the first time it ran alone.
                app.contentResolver.takePersistableUriPermission(
                    it,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                )
                it.toString()
            } catch (_: SecurityException) {
                null
            }
        }
        pendingFolder?.complete(kept)
        pendingFolder = null
    }

    override suspend fun pickFolder(): String? = withContext(Dispatchers.Main) {
        val launcher = folderLauncher ?: return@withContext null
        val answer = CompletableDeferred<String?>()
        pendingFolder?.complete(null)
        pendingFolder = answer
        launcher.launch(null)
        answer.await()
    }

    override val needsNotificationPermission: Boolean
        get() = Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(app, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED

    override suspend fun requestNotifications(): Boolean = withContext(Dispatchers.Main) {
        // Stated here as well as in the property, where lint cannot follow it.
        if (Build.VERSION.SDK_INT < 33 || !needsNotificationPermission) return@withContext true
        val launcher = notificationLauncher ?: return@withContext false
        val answer = CompletableDeferred<Boolean>()
        pendingNotifications?.complete(false)
        pendingNotifications = answer
        launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        answer.await()
    }

    override fun isBatteryUnrestricted(): Boolean =
        app.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(app.packageName)

    // The direct request is the one-tap path; the app copies on a schedule the
    // user set up, which is the use Android's policy names for it.
    @SuppressLint("BatteryLife")
    override fun openBatterySettings() {
        val context: Context = activity ?: app
        val newTask = if (context === app) Intent.FLAG_ACTIVITY_NEW_TASK else 0
        val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, "package:${app.packageName}".toUri())
            .addFlags(newTask)
        try {
            context.startActivity(direct)
        } catch (_: ActivityNotFoundException) {
            // Some builds remove the direct request; the list of apps is always there.
            context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS).addFlags(newTask))
        }
    }

    override fun areNotificationsEnabled(): Boolean = NotificationManagerCompat.from(app).areNotificationsEnabled()

    override fun openNotificationSettings() {
        val context: Context = activity ?: app
        val newTask = if (context === app) Intent.FLAG_ACTIVITY_NEW_TASK else 0
        context.startActivity(
            Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, app.packageName)
                .addFlags(newTask),
        )
    }
}

/** The tree picker, asking for a grant that survives a restart and covers writing. */
private class PersistableTree : ActivityResultContracts.OpenDocumentTree() {
    override fun createIntent(context: Context, input: Uri?): Intent =
        super.createIntent(context, input).addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or
                Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION,
        )
}
