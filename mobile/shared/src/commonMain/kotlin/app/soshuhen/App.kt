package app.soshuhen

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import app.soshuhen.core.AppGraph
import coil3.ImageLoader
import coil3.compose.setSingletonImageLoaderFactory
import coil3.network.ktor3.KtorNetworkFetcherFactory
import app.soshuhen.onboarding.OnboardingScreen
import app.soshuhen.onboarding.OnboardingViewModel
import app.soshuhen.ui.theme.SoshuhenTheme

@Composable
fun App(graph: AppGraph) {
    // Covers through the app's own client: same timeouts, and no second HTTP
    // stack that could be pointed anywhere but the server.
    setSingletonImageLoaderFactory { context ->
        ImageLoader.Builder(context)
            .components { add(KtorNetworkFetcherFactory(httpClient = { graph.client })) }
            .build()
    }
    SoshuhenTheme {
        // A sentinel distinguishes "not read yet" from "nothing saved", so a
        // returning user never sees onboarding flash before the shell.
        val saved by graph.store.saved.collectAsState(initial = Loading)
        Scaffold { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                when (saved) {
                    Loading -> Unit
                    null -> OnboardingScreen(
                        viewModel { OnboardingViewModel(graph.scanner, graph.probe, graph.network, graph.store) },
                    )
                    else -> {
                        LaunchedEffect(Unit) { graph.session.refreshLocation() }
                        MainShell(graph)
                    }
                }
            }
        }
    }
}

private object Loading
