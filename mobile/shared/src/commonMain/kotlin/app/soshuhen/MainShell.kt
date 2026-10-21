package app.soshuhen

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.ExperimentalMaterial3AdaptiveApi
import androidx.compose.material3.adaptive.layout.AnimatedPane
import androidx.compose.material3.adaptive.layout.ListDetailPaneScaffoldRole
import androidx.compose.material3.adaptive.layout.ListDetailPaneScaffold
import androidx.compose.material3.adaptive.navigation.rememberListDetailPaneScaffoldNavigator
import androidx.compose.material3.adaptive.navigationsuite.NavigationSuiteScaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.backhandler.BackHandler
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.soshuhen.core.AppGraph
import app.soshuhen.detail.SeriesDetailScreen
import app.soshuhen.detail.SeriesDetailViewModel
import app.soshuhen.library.LibraryScreen
import app.soshuhen.library.LibraryViewModel
import app.soshuhen.settings.SettingsScreen
import app.soshuhen.settings.SettingsViewModel
import app.soshuhen.ui.Glyph
import app.soshuhen.ui.theme.Tokens
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable object LibraryRoute
@Serializable object SettingsRoute

/**
 * The app once a server is chosen. NavigationSuiteScaffold draws a bottom bar
 * on a phone and a rail on a tablet or a phone on its side, and the library is
 * a list-detail pair that sits side by side when there is room: window size
 * decides, not device type.
 */
@Composable
fun MainShell(graph: AppGraph, appVersion: String) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val onSettings = entry?.destination?.hasRoute(SettingsRoute::class) == true
    NavigationSuiteScaffold(
        navigationSuiteItems = {
            item(
                selected = !onSettings,
                onClick = { nav.navigate(LibraryRoute) { popUpTo(LibraryRoute) { inclusive = true } } },
                icon = { Glyph("▦") },
                label = { Text("Library") },
            )
            item(
                selected = onSettings,
                onClick = { nav.navigate(SettingsRoute) { launchSingleTop = true } },
                icon = { Glyph("⚙") },
                label = { Text("Settings") },
            )
        },
    ) {
        NavHost(nav, startDestination = LibraryRoute) {
            composable<LibraryRoute> { LibraryPanes(graph) }
            composable<SettingsRoute> {
                SettingsScreen(viewModel { SettingsViewModel(graph.session.api, graph.store) }, appVersion)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3AdaptiveApi::class, ExperimentalComposeUiApi::class)
@Composable
private fun LibraryPanes(graph: AppGraph) {
    val navigator = rememberListDetailPaneScaffoldNavigator<Long>()
    val scope = rememberCoroutineScope()
    val api by graph.session.api.collectAsStateWithLifecycle()
    val coverUrl = { id: Long -> api?.coverUrl(id).orEmpty() }
    // On a phone the detail replaces the grid, so back has to bring it back
    // rather than leave the app.
    BackHandler(enabled = navigator.canNavigateBack()) { scope.launch { navigator.navigateBack() } }
    ListDetailPaneScaffold(
        directive = navigator.scaffoldDirective,
        value = navigator.scaffoldValue,
        listPane = {
            AnimatedPane {
                LibraryScreen(
                    model = viewModel { LibraryViewModel(graph.session.api, graph.local) },
                    coverUrl = coverUrl,
                    onOpen = { id -> scope.launch { navigator.navigateTo(ListDetailPaneScaffoldRole.Detail, id) } },
                )
            }
        },
        detailPane = {
            AnimatedPane {
                val id = navigator.currentDestination?.contentKey
                if (id == null) {
                    Box(Modifier.fillMaxSize(), Alignment.Center) {
                        Text("Pick a series", color = Tokens.onSurfaceVariant, style = MaterialTheme.typography.bodyLarge)
                    }
                } else {
                    // Keyed by id, so opening another series gets its own model.
                    SeriesDetailScreen(
                        viewModel(key = "series-$id") { SeriesDetailViewModel(id, graph.session.api, graph.local) },
                        coverUrl(id),
                    )
                }
            }
        },
    )
}
