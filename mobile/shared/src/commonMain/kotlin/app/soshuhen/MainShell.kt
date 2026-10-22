package app.soshuhen

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.ExperimentalMaterial3AdaptiveApi
import androidx.compose.material3.adaptive.layout.AnimatedPane
import androidx.compose.material3.adaptive.layout.ListDetailPaneScaffoldRole
import androidx.compose.material3.adaptive.layout.ListDetailPaneScaffold
import androidx.compose.material3.adaptive.layout.ListDetailPaneScaffoldDefaults
import androidx.compose.material3.adaptive.layout.calculateThreePaneScaffoldValue
import androidx.compose.material3.adaptive.navigation.rememberListDetailPaneScaffoldNavigator
import androidx.compose.material3.adaptive.navigationsuite.NavigationSuiteScaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import androidx.navigation.toRoute
import app.soshuhen.core.AppGraph
import app.soshuhen.core.Platform
import app.soshuhen.detail.SeriesDetailScreen
import app.soshuhen.detail.SeriesDetailViewModel
import app.soshuhen.library.LibraryScreen
import app.soshuhen.library.LibraryViewModel
import app.soshuhen.reader.ReaderScreen
import app.soshuhen.reader.ReaderViewModel
import app.soshuhen.settings.SettingsScreen
import app.soshuhen.settings.SettingsViewModel
import app.soshuhen.ui.WebGlyph
import app.soshuhen.ui.WebIcon
import app.soshuhen.ui.theme.mono
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.NavigationRailItemDefaults
import androidx.compose.material3.adaptive.navigationsuite.NavigationSuiteDefaults
import androidx.compose.ui.graphics.Color
import app.soshuhen.ui.theme.Tokens
import app.soshuhen.updates.UpdatesScreen
import app.soshuhen.updates.UpdatesViewModel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable object LibraryRoute
@Serializable object UpdatesRoute
@Serializable object SettingsRoute

@Serializable object ShellRoute

/** [page] is [SAVED_PLACE] when the reader should find the chapter's own saved place. */
@Serializable data class ReaderRoute(val seriesId: Long, val chapterId: Long, val page: Int, val title: String)

// Navigation arguments cannot be a nullable Int.
private const val SAVED_PLACE = -1

/**
 * The app once a server is chosen. The reader is a route beside the shell
 * rather than inside it, so a page fills the screen with no navigation bar.
 */
@Composable
fun MainShell(
    graph: AppGraph,
    platform: Platform,
    appVersion: String,
    importNow: () -> Unit,
    // A series asked for from outside the app, by tapping its notification.
    requestedSeries: StateFlow<Long?>,
    onRequestHandled: () -> Unit,
) {
    val root = rememberNavController()
    var opening by remember { mutableStateOf<Long?>(null) }
    val requested by requestedSeries.collectAsStateWithLifecycle()
    LaunchedEffect(requested) {
        requested?.let { id ->
            // Out of the reader first: the series opens in the shell.
            root.popBackStack(ShellRoute, inclusive = false)
            opening = id
            onRequestHandled()
        }
    }
    NavHost(root, startDestination = ShellRoute) {
        composable<ShellRoute> {
            Shell(graph, platform, appVersion, importNow, opening, { opening = it }) { seriesId, chapterId, page, title ->
                root.navigate(ReaderRoute(seriesId, chapterId, page ?: SAVED_PLACE, title))
            }
        }
        composable<ReaderRoute> { entry ->
            val route = entry.toRoute<ReaderRoute>()
            ReaderScreen(
                viewModel {
                    ReaderViewModel(
                        route.seriesId, route.chapterId, route.page.takeIf { it != SAVED_PLACE },
                        graph.session.api, graph.session.atHome, graph.local, graph.folder, graph.pages, graph.outbox,
                    )
                },
                route.title,
                onBack = { root.popBackStack() },
            )
        }
    }
}

/**
 * NavigationSuiteScaffold draws a bottom bar on a phone and a rail on a tablet
 * or a phone on its side, and the library is a list-detail pair that sits side
 * by side when there is room: window size decides, not device type.
 */
@Composable
private fun Shell(
    graph: AppGraph,
    platform: Platform,
    appVersion: String,
    importNow: () -> Unit,
    opening: Long?,
    setOpening: (Long?) -> Unit,
    onRead: (seriesId: Long, chapterId: Long, page: Int?, title: String) -> Unit,
) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val onSettings = entry?.destination?.hasRoute(SettingsRoute::class) == true
    val onUpdates = entry?.destination?.hasRoute(UpdatesRoute::class) == true
    val goToLibrary = { nav.navigate(LibraryRoute) { popUpTo(LibraryRoute) { inclusive = true } } }
    // Marking is what makes a series worth copying, so a new mark starts a run
    // instead of waiting up to an hour. The first emission is only what was
    // already marked.
    LaunchedEffect(Unit) {
        var known: Set<Long>? = null
        graph.local.markedIds().collect { ids ->
            if (known != null && (ids - known!!).isNotEmpty()) importNow()
            known = ids
        }
    }
    LaunchedEffect(opening) {
        if (opening != null) goToLibrary()
    }
    // AppShell.tsx's bottom bar: surface-container-lowest, no pill behind the
    // current item, which is told apart by its primary tint alone.
    val barItem = NavigationBarItemDefaults.colors(
        selectedIconColor = Tokens.primary, selectedTextColor = Tokens.primary, indicatorColor = Color.Transparent,
        unselectedIconColor = Tokens.onSurfaceVariant, unselectedTextColor = Tokens.onSurfaceVariant,
    )
    val railItem = NavigationRailItemDefaults.colors(
        selectedIconColor = Tokens.primary, selectedTextColor = Tokens.primary, indicatorColor = Color.Transparent,
        unselectedIconColor = Tokens.onSurfaceVariant, unselectedTextColor = Tokens.onSurfaceVariant,
    )
    val itemColors = NavigationSuiteDefaults.itemColors(navigationBarItemColors = barItem, navigationRailItemColors = railItem)
    val label: @Composable (String) -> Unit = { Text(it, style = MaterialTheme.typography.labelSmall.mono()) }
    NavigationSuiteScaffold(
        navigationSuiteColors = NavigationSuiteDefaults.colors(
            navigationBarContainerColor = Tokens.surfaceContainerLowest,
            navigationRailContainerColor = Tokens.surfaceContainerLowest,
        ),
        navigationSuiteItems = {
            item(
                selected = !onSettings && !onUpdates,
                onClick = { goToLibrary() },
                icon = { WebGlyph(WebIcon.Book, LocalContentColor.current) },
                label = { label("Library") },
                colors = itemColors,
            )
            item(
                selected = onUpdates,
                onClick = { nav.navigate(UpdatesRoute) { launchSingleTop = true } },
                icon = { WebGlyph(WebIcon.Bell, LocalContentColor.current) },
                label = { label("Updates") },
                colors = itemColors,
            )
            item(
                selected = onSettings,
                onClick = { nav.navigate(SettingsRoute) { launchSingleTop = true } },
                icon = { WebGlyph(WebIcon.Settings, LocalContentColor.current) },
                label = { label("Settings") },
                colors = itemColors,
            )
        },
    ) {
        NavHost(nav, startDestination = LibraryRoute) {
            composable<LibraryRoute> { LibraryPanes(graph, opening, { setOpening(null) }, importNow, onRead) }
            composable<UpdatesRoute> {
                val api by graph.session.api.collectAsStateWithLifecycle()
                UpdatesScreen(
                    viewModel { UpdatesViewModel(graph.local) },
                    graph.local,
                    coverUrl = { id -> api?.coverUrl(id).orEmpty() },
                    onOpen = { id -> setOpening(id) },
                )
            }
            composable<SettingsRoute> {
                SettingsScreen(viewModel { SettingsViewModel(graph.session.api, graph.store, platform) }, appVersion)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3AdaptiveApi::class, ExperimentalComposeUiApi::class)
@Composable
private fun LibraryPanes(
    graph: AppGraph,
    opening: Long?,
    onOpened: () -> Unit,
    importNow: () -> Unit,
    onRead: (seriesId: Long, chapterId: Long, page: Int?, title: String) -> Unit,
) {
    val navigator = rememberListDetailPaneScaffoldNavigator<Long>()
    val scope = rememberCoroutineScope()
    val api by graph.session.api.collectAsStateWithLifecycle()
    val atHome by graph.session.atHome.collectAsStateWithLifecycle()
    val coverUrl = { id: Long -> api?.coverUrl(id).orEmpty() }
    LaunchedEffect(opening) {
        opening?.let { id ->
            navigator.navigateTo(ListDetailPaneScaffoldRole.Detail, id)
            onOpened()
        }
    }
    // On a phone the detail replaces the grid, so back has to bring it back
    // rather than leave the app.
    BackHandler(enabled = navigator.canNavigateBack()) { scope.launch { navigator.navigateBack() } }
    // With nothing picked the library takes the whole width, as the web's does;
    // the split only appears once there is a series to put beside it.
    val picked = navigator.currentDestination?.contentKey != null
    val directive = if (picked) navigator.scaffoldDirective else navigator.scaffoldDirective.copy(maxHorizontalPartitions = 1)
    ListDetailPaneScaffold(
        directive = directive,
        value = if (picked) {
            navigator.scaffoldValue
        } else {
            calculateThreePaneScaffoldValue(1, ListDetailPaneScaffoldDefaults.adaptStrategies(), navigator.currentDestination)
        },
        listPane = {
            AnimatedPane {
                LibraryScreen(
                    model = viewModel { LibraryViewModel(graph.session.api, graph.local, graph.session.atHome) },
                    store = graph.local,
                    coverUrl = coverUrl,
                    onOpen = { id -> scope.launch { navigator.navigateTo(ListDetailPaneScaffoldRole.Detail, id) } },
                    onRefreshed = importNow,
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
                        viewModel(key = "series-$id") { SeriesDetailViewModel(id, graph.session.api, graph.session.atHome, graph.local, graph.library) },
                        coverUrl(id),
                        home = atHome && api != null,
                        onRead = { chapterId, page, title -> onRead(id, chapterId, page, title) },
                    )
                }
            }
        },
    )
}
