package app.soshuhen.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.ui.MonoLabel
import app.soshuhen.ui.SectionHeader
import app.soshuhen.ui.WebButton
import app.soshuhen.ui.WebCard
import app.soshuhen.ui.WebGlyph
import app.soshuhen.ui.WebIcon
import app.soshuhen.ui.WebToggle
import app.soshuhen.ui.theme.Tokens
import app.soshuhen.ui.theme.mono

/**
 * frontend/src/features/settings/SettingsPage.tsx's shape: the title card,
 * then one section per concern, each a SectionHeader over its cards.
 */
@Composable
fun SettingsScreen(model: SettingsViewModel, appVersion: String) {
    val server by model.server.collectAsStateWithLifecycle()
    val volumeKeys by model.volumeKeys.collectAsStateWithLifecycle()
    val volumeInvert by model.volumeInvert.collectAsStateWithLifecycle()
    val folder by model.folder.collectAsStateWithLifecycle()
    val unrestricted by model.batteryUnrestricted.collectAsStateWithLifecycle()
    LifecycleResumeEffect(model) {
        model.refreshBattery()
        onPauseOrDispose { }
    }
    BoxWithConstraints(Modifier.fillMaxSize().background(Tokens.background).statusBarsPadding()) {
        val side = if (maxWidth < Tokens.box.sm) Tokens.space.lg else Tokens.space.margin
        Column(
            // Scrolls: with the device card a short phone in landscape no longer fits it all.
            Modifier.verticalScroll(rememberScrollState())
                .padding(start = side, end = side, top = Tokens.space.xl, bottom = Tokens.space.xxl)
                .widthIn(max = Tokens.contentMaxWidth),
            verticalArrangement = Arrangement.spacedBy(Tokens.space.xxl),
        ) {
            WebCard(Modifier.fillMaxWidth(), spacing = Tokens.space.xs) {
                MonoLabel(
                    "Soshuhen for Android",
                    Tokens.primary,
                    Modifier.background(Tokens.surfaceContainerHigh, CircleShape)
                        .padding(horizontal = Tokens.space.sm, vertical = Tokens.space.xxs),
                    uppercase = true,
                )
                Text("Settings", style = MaterialTheme.typography.headlineLarge, color = Tokens.onSurface)
                Text(
                    "The server this phone reads from, where its chapters are kept, and how the reader turns pages.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Tokens.onSurfaceVariant,
                )
            }

            Section {
                SectionHeader(WebIcon.Server, "Server", "The Soshuhen this phone reads from")
                val card = server
                // ProviderCard.tsx: a tile, a name, then the state on an inset panel.
                WebCard(Modifier.fillMaxWidth()) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                        Box(
                            Modifier.size(Tokens.box.providerTile)
                                .background(Tokens.surfaceContainerHighest, RoundedCornerShape(Tokens.radius.lg)),
                            contentAlignment = Alignment.Center,
                        ) { WebGlyph(WebIcon.Server, Tokens.primary, Tokens.icon.xl) }
                        Column(Modifier.weight(1f)) {
                            Text(card?.identity?.name ?: "Soshuhen", style = MaterialTheme.typography.titleMedium, color = Tokens.onSurface)
                            card?.let { Text(it.baseUrl, style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant) }
                        }
                    }
                    if (card != null) {
                        Inset {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                StatusDot(if (card.identity != null) Tokens.secondary else Tokens.error)
                                Text(
                                    if (card.identity != null) "Connected" else "Not reachable right now",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Tokens.onSurfaceVariant,
                                    modifier = Modifier.weight(1f).padding(start = Tokens.space.xsPlus),
                                )
                                card.identity?.let { MonoLabel(it.version, Tokens.onSurface) }
                            }
                        }
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        WebButton("Change server", model::forget, small = true, icon = WebIcon.Link)
                    }
                }
            }

            Section {
                SectionHeader(WebIcon.Folder, "On this device", "Where chapters are copied, and what lets them arrive")
                WebCard(Modifier.fillMaxWidth(), spacing = Tokens.space.lg) {
                    Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                        Text("Chapters folder", style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant)
                        // The web's read-only field: lowest surface, mono, tertiary.
                        Text(
                            folder ?: "No folder picked",
                            style = MaterialTheme.typography.labelMedium.mono(),
                            color = Tokens.tertiary,
                            modifier = Modifier.fillMaxWidth()
                                .background(Tokens.surfaceContainerLowest, RoundedCornerShape(Tokens.radius.lg))
                                .padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm),
                        )
                        Text(
                            "Chapters already copied stay where they are. New ones go to the folder picked here.",
                            style = MaterialTheme.typography.bodySmall,
                            color = Tokens.onSurfaceVariant,
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        WebButton("Change folder", model::changeFolder, small = true, icon = WebIcon.Folder)
                    }
                    Inset {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            StatusDot(if (unrestricted) Tokens.secondary else Tokens.warning)
                            Text(
                                if (unrestricted) "Background copies: unrestricted" else "Background copies: Android may put the app to sleep",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (unrestricted) Tokens.onSurfaceVariant else Tokens.warning,
                                modifier = Modifier.weight(1f).padding(start = Tokens.space.xsPlus),
                            )
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                            WebButton("Open battery settings", model::openBatterySettings, small = true, icon = WebIcon.Bolt)
                        }
                    }
                }
            }

            Section {
                SectionHeader(WebIcon.Book, "Reader", "How the volume keys turn pages")
                WebCard(Modifier.fillMaxWidth(), spacing = Tokens.space.md) {
                    WebToggle("Volume keys turn pages", volumeKeys, model::setVolumeKeys)
                    // Off while the keys do nothing: inverting them would be a choice with no effect.
                    WebToggle("Invert volume keys", volumeInvert, model::setVolumeInvert, enabled = volumeKeys)
                }
            }

            MonoLabel("Soshuhen for Android $appVersion")
        }
    }
}

@Composable
private fun Section(content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) { content() }
}

/** ProviderCard's inset status panel (rounded-lg bg-surface-container-low p-space-md). */
@Composable
private fun Inset(content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxWidth()
            .background(Tokens.surfaceContainerLow, RoundedCornerShape(Tokens.radius.lg))
            .padding(Tokens.space.lg),
        verticalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) { content() }
}

@Composable
private fun StatusDot(color: Color) {
    Box(Modifier.size(Tokens.box.dot).background(color, CircleShape))
}
