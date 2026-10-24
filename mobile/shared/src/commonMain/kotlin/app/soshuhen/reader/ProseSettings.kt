package app.soshuhen.reader

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.currentWindowAdaptiveInfoV2
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.window.core.layout.WindowSizeClass
import app.soshuhen.ui.theme.Tokens
import kotlin.math.roundToInt

private val bar = Tokens.surfaceContainer.copy(alpha = Tokens.reader.barAlpha)

/** The manga reader's chrome, with the place shown as a share of the book: a novel has no fixed pages. */
@Composable
internal fun ProseChrome(
    ui: ProseUi,
    seriesTitle: String,
    model: ProseReaderViewModel,
    onBack: () -> Unit,
    onSettings: () -> Unit,
) {
    Box(Modifier.fillMaxSize()) {
        Row(
            Modifier.align(Alignment.TopCenter).fillMaxWidth().swallowTaps().background(bar)
                .padding(horizontal = Tokens.space.md, vertical = Tokens.space.sm),
            horizontalArrangement = Arrangement.spacedBy(Tokens.space.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GlyphButton("←", "Back to the series", onBack, Modifier.padding(Tokens.space.xs))
            Column(Modifier.weight(1f)) {
                Text(
                    seriesTitle, style = MaterialTheme.typography.titleMedium, color = Tokens.onSurface,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
                Text(
                    ui.title, style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Column(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth().swallowTaps().background(bar)
                .padding(start = Tokens.space.md, end = Tokens.space.md, top = Tokens.space.sm, bottom = Tokens.space.md),
            verticalArrangement = Arrangement.spacedBy(Tokens.space.sm),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                RoundButton("‹", "Previous", enabled = ui.previous != null) { ui.previous?.let(model::open) }
                PlaceSlider(ui, rtl = ui.mode == "paged_rtl", onSeek = { model.moveTo(ui.book.positionAtChar(it)) }, Modifier.weight(1f))
                RoundButton("›", "Next", enabled = ui.next != null) { ui.next?.let(model::open) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
                GlyphButton("⚙", "Reading settings", onSettings, Modifier.padding(Tokens.space.sm))
            }
        }
    }
}

@Composable
private fun PlaceSlider(ui: ProseUi, rtl: Boolean, onSeek: (Int) -> Unit, modifier: Modifier = Modifier) {
    val length = ui.book.length()
    val at = ui.book.charsBefore(ui.position)
    val percent = if (length > 1) (at * 100f / (length - 1)).roundToInt() else 100
    Row(
        modifier.clip(CircleShape).background(Tokens.surfaceContainerHighest)
            .padding(horizontal = Tokens.space.md, vertical = Tokens.space.xs),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) {
        // The slider runs the way the pages turn, as the manga reader's does.
        CompositionLocalProvider(LocalLayoutDirection provides if (rtl) LayoutDirection.Rtl else LayoutDirection.Ltr) {
            Slider(
                value = at.toFloat(),
                onValueChange = { onSeek(it.roundToInt()) },
                valueRange = 0f..maxOf(length - 1, 1).toFloat(),
                enabled = length > 1,
                colors = SliderDefaults.colors(
                    thumbColor = Tokens.primary,
                    activeTrackColor = Tokens.primary,
                    inactiveTrackColor = Tokens.outlineVariant,
                ),
                modifier = Modifier.weight(1f).semantics { contentDescription = "Place in the book" },
            )
        }
        Text(
            "$percent%", Modifier.width(Tokens.reader.pageNumberWidth), textAlign = TextAlign.End,
            style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace, color = Tokens.onSurface,
        )
    }
}

private val directions = listOf(
    "paged_ltr" to "Paged (left to right)",
    "paged_rtl" to "Paged (right to left)",
    "double" to "Double page",
    "long_strip" to "Scroll",
)

/** Direction for this series; type and paper for every novel on the device. */
@Composable
internal fun ProseSettings(ui: ProseUi, model: ProseReaderViewModel, onClose: () -> Unit) {
    // Two pages side by side are offered where the manga reader offers them.
    val wide = currentWindowAdaptiveInfoV2().windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_MEDIUM_LOWER_BOUND)
    val offered = directions.filter { it.first != "double" || wide || ui.mode == "double" }
    val style = ui.style
    ReaderSheet("Reading settings", onClose) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            OptionGroup("Direction", offered, ui.mode) { model.setMode(it) }
            OptionGroup("Font", PROSE_FONTS, style.font) { model.setStyle(style.copy(font = it)) }
            Column(Modifier.padding(top = Tokens.space.md)) {
                Text(
                    "Size", Modifier.padding(bottom = Tokens.space.sm),
                    style = MaterialTheme.typography.labelMedium, color = Tokens.onSurfaceVariant,
                )
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.md)) {
                    RoundButton("−", "Smaller text", enabled = style.fontSize > PROSE_SIZES.first) {
                        model.setStyle(style.copy(fontSize = style.fontSize - PROSE_SIZES.step))
                    }
                    Text(
                        "${style.fontSize}", style = MaterialTheme.typography.titleMedium,
                        fontFamily = FontFamily.Monospace, color = Tokens.onSurface,
                    )
                    RoundButton("+", "Larger text", enabled = style.fontSize < PROSE_SIZES.last) {
                        model.setStyle(style.copy(fontSize = style.fontSize + PROSE_SIZES.step))
                    }
                }
            }
            OptionGroup("Background", PROSE_BACKGROUNDS, style.background) { model.setStyle(style.copy(background = it)) }
            Text(
                "Direction is kept for this series; font, size and background for every novel on this device.",
                Modifier.padding(top = Tokens.space.lg),
                style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant,
            )
        }
    }
}
