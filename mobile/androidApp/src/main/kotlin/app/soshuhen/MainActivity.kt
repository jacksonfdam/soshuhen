package app.soshuhen

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import app.soshuhen.core.EXTRA_SERIES_ID
import app.soshuhen.core.ImportScheduler
import kotlinx.coroutines.flow.MutableStateFlow

class MainActivity : ComponentActivity() {
    // A tapped notification names a series; the shell opens it once it exists,
    // which may be after onboarding.
    private val requestedSeries = MutableStateFlow<Long?>(null)

    private val askForNotifications =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        // Before super.onCreate: the splash theme has to be swapped for the
        // app's before the first frame, or Android 10 and 11 flash it.
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Not on a recreation: the intent still holds the extra after a rotation,
        // and opening the series again would undo wherever the user had gone.
        if (savedInstanceState == null) readSeries(intent)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            askForNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        ImportScheduler.runNow(this)
        val graph = (application as SoshuhenApplication).graph
        setContent {
            App(
                graph,
                BuildConfig.VERSION_NAME,
                importNow = { ImportScheduler.runNow(this) },
                requestedSeries = requestedSeries,
                onRequestHandled = { requestedSeries.value = null },
            )
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        readSeries(intent)
    }

    private fun readSeries(intent: Intent?) {
        val id = intent?.getLongExtra(EXTRA_SERIES_ID, -1L) ?: -1L
        if (id >= 0) requestedSeries.value = id
    }
}
