package app.soshuhen

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // Before super.onCreate: the splash theme has to be swapped for the
        // app's before the first frame, or Android 10 and 11 flash it.
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val graph = (application as SoshuhenApplication).graph
        setContent { App(graph, BuildConfig.VERSION_NAME) }
    }
}
