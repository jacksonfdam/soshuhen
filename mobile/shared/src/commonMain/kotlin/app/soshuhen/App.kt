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
import app.soshuhen.core.Platform
import kotlinx.coroutines.flow.StateFlow
import coil3.ImageLoader
import coil3.compose.setSingletonImageLoaderFactory
import coil3.disk.DiskCache
import coil3.network.CacheStrategy
import coil3.network.NetworkRequest
import coil3.network.NetworkResponse
import coil3.network.ktor3.KtorNetworkFetcherFactory
import coil3.request.Options
import app.soshuhen.onboarding.OnboardingScreen
import app.soshuhen.onboarding.OnboardingViewModel
import app.soshuhen.onboarding.SetupScreen
import app.soshuhen.onboarding.SetupViewModel
import app.soshuhen.ui.theme.SoshuhenTheme

@Composable
fun App(
    graph: AppGraph,
    platform: Platform,
    appVersion: String,
    importNow: () -> Unit,
    requestedSeries: StateFlow<Long?>,
    onRequestHandled: () -> Unit,
) {
    // Covers through the app's own client: same timeouts, and no second HTTP
    // stack that could be pointed anywhere but the server.
    setSingletonImageLoaderFactory { context ->
        ImageLoader.Builder(context)
            .components {
                add(KtorNetworkFetcherFactory(httpClient = { graph.client }, cacheStrategy = { KeepCovers }))
            }
            // Explicit so covers survive offline and the size is ours to state.
            .diskCache {
                DiskCache.Builder()
                    .directory(graph.cacheDir / "covers")
                    .maxSizeBytes(COVER_CACHE_BYTES)
                    .build()
            }
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
                    null -> {
                        val model = viewModel { OnboardingViewModel(graph.scanner, graph.probe, graph.network, graph.store) }
                        LaunchedEffect(Unit) { model.onShown() }
                        OnboardingScreen(model)
                    }
                    else -> {
                        val setup = viewModel { SetupViewModel(graph.store, platform, graph.folder) }
                        val ready by setup.ready.collectAsState()
                        val step by setup.step.collectAsState()
                        when {
                            !ready -> Unit
                            // The shell does not open without a folder: every screen
                            // after this one assumes there is somewhere to copy to.
                            step != null -> SetupScreen(setup)
                            else -> MainShell(graph, platform, appVersion, importNow, requestedSeries, onRequestHandled)
                        }
                    }
                }
            }
        }
    }
}

private object Loading

private const val COVER_CACHE_BYTES = 256L * 1024 * 1024

/**
 * The server sends max-age=86400 on covers. Honoured, Coil would revalidate
 * after a day, fail away from home and show initials. The price is that a
 * changed cover appears only once the app's cache is cleared.
 */
private object KeepCovers : CacheStrategy {
    override suspend fun read(
        cacheResponse: NetworkResponse,
        networkRequest: NetworkRequest,
        options: Options,
    ) = CacheStrategy.ReadResult(cacheResponse)

    override suspend fun write(
        cacheResponse: NetworkResponse?,
        networkRequest: NetworkRequest,
        networkResponse: NetworkResponse,
        options: Options,
    ) = CacheStrategy.WriteResult(networkResponse)
}
