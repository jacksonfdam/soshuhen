package app.soshuhen

import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.navigationsuite.NavigationSuiteScaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.soshuhen.core.AppGraph
import app.soshuhen.library.LibraryScreen
import app.soshuhen.library.LibraryViewModel
import app.soshuhen.ui.Glyph
import kotlinx.serialization.Serializable

@Serializable object LibraryRoute
@Serializable data class SeriesRoute(val id: Long)
@Serializable object SettingsRoute

/**
 * The app once a server is chosen. NavigationSuiteScaffold draws a bottom bar
 * on a phone and a rail on a tablet or a phone on its side, which is the rule
 * the design asks for: window size decides, not device type.
 */
@Composable
fun MainShell(graph: AppGraph) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val api by graph.session.api.collectAsStateWithLifecycle()
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
            composable<LibraryRoute> {
                LibraryScreen(
                    model = viewModel { LibraryViewModel(graph.session.api) },
                    coverUrl = { id -> api?.coverUrl(id).orEmpty() },
                    onOpen = { id -> nav.navigate(SeriesRoute(id)) },
                )
            }
            composable<SeriesRoute> { Text("Series") }
            composable<SettingsRoute> { Text("Settings") }
        }
    }
}
