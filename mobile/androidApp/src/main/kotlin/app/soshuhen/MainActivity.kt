package app.soshuhen

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import app.soshuhen.core.EXTRA_SERIES_ID
import app.soshuhen.core.ImportScheduler
import app.soshuhen.reader.ReaderKeys
import app.soshuhen.reader.volumeKey
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

    // Keys whose press a reader took. Their release is swallowed too, or the
    // system would see a lone ACTION_UP and still show the volume panel.
    private val consumed = mutableSetOf<Int>()

    // Activity.dispatchKeyEvent is public; lint objects only because androidx.core's
    // ComponentActivity overrides it under @RestrictTo, which an override cannot avoid.
    @SuppressLint("RestrictedApi")
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val code = event.keyCode
        if (code != KeyEvent.KEYCODE_VOLUME_DOWN && code != KeyEvent.KEYCODE_VOLUME_UP) return super.dispatchKeyEvent(event)
        val graph = (application as SoshuhenApplication).graph
        when (event.action) {
            KeyEvent.ACTION_DOWN -> {
                if (event.repeatCount > 0) {
                    // A held key turns one page, not a page every 50 ms.
                    if (code in consumed) return true
                } else if (graph.volumeKeys.value) {
                    val key = volumeKey(down = code == KeyEvent.KEYCODE_VOLUME_DOWN, inverted = graph.volumeInvert.value)
                    // Unclaimed outside a reader, so the volume still works everywhere else.
                    if (ReaderKeys.emit(key)) {
                        consumed += code
                        return true
                    }
                }
            }
            KeyEvent.ACTION_UP -> if (consumed.remove(code)) return true
        }
        return super.dispatchKeyEvent(event)
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
