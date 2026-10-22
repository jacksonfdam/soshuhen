package app.soshuhen.reader

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.currentWindowAdaptiveInfoV2
import androidx.compose.material3.SheetValue
import androidx.compose.material3.rememberBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.window.core.layout.WindowSizeClass
import app.soshuhen.api.ReaderPrefs
import app.soshuhen.core.Availability
import app.soshuhen.core.ChapterRow
import app.soshuhen.ui.theme.Tokens
import kotlin.math.roundToInt

internal enum class Panel { Settings, Chapters }

private val bar = Tokens.surfaceContainer.copy(alpha = Tokens.reader.barAlpha)

/**
 * The web's TabletChrome, the reader's chrome below xl: hidden until a tap in
 * the middle of the page, a title bar on top and the controls at the bottom.
 */
@Composable
internal fun ReaderChrome(
    ui: ReaderUi,
    seriesTitle: String,
    rtl: Boolean,
    onBack: () -> Unit,
    onSeek: (Int) -> Unit,
    onOpenChapter: (Long) -> Unit,
    onPanel: (Panel) -> Unit,
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
                    "Ch. ${formatChapter(ui.chapter.number)}" + (ui.chapter.title?.let { " - $it" } ?: ""),
                    style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant,
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
                RoundButton("‹", "Previous chapter", enabled = ui.previous != null) { ui.previous?.let(onOpenChapter) }
                PageSlider(ui.page, ui.pageCount, rtl, onSeek, Modifier.weight(1f))
                RoundButton("›", "Next chapter", enabled = ui.next != null) { ui.next?.let(onOpenChapter) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
                GlyphButton("☰", "Chapters", { onPanel(Panel.Chapters) }, Modifier.padding(Tokens.space.sm))
                GlyphButton("⚙", "Reader settings", { onPanel(Panel.Settings) }, Modifier.padding(Tokens.space.sm))
            }
        }
    }
}

// A tap on a bar's empty part belongs to the bar, not to the page beneath it.
private fun Modifier.swallowTaps() = pointerInput(Unit) { detectTapGestures { } }

@Composable
private fun GlyphButton(glyph: String, label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        Modifier.clip(RoundedCornerShape(Tokens.radius.lg)).clickable(onClick = onClick)
            .semantics { contentDescription = label }.then(modifier),
        contentAlignment = Alignment.Center,
    ) {
        Text(glyph, style = MaterialTheme.typography.titleLarge, color = Tokens.onSurface)
    }
}

@Composable
private fun RoundButton(glyph: String, label: String, enabled: Boolean, onClick: () -> Unit) {
    Box(
        Modifier.size(Tokens.reader.control).clip(CircleShape).background(Tokens.surfaceContainerHighest)
            .clickable(enabled = enabled, onClick = onClick).semantics { contentDescription = label }
            .alpha(if (enabled) 1f else Tokens.dimmed),
        contentAlignment = Alignment.Center,
    ) {
        Text(glyph, style = MaterialTheme.typography.titleLarge, color = Tokens.onSurface)
    }
}

/** The web's PageSlider: page number, slider, page count, in one pill. */
@Composable
private fun PageSlider(page: Int, pageCount: Int, rtl: Boolean, onSeek: (Int) -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier.clip(CircleShape).background(Tokens.surfaceContainerHighest)
            .padding(horizontal = Tokens.space.md, vertical = Tokens.space.xs),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) {
        Text(
            "${page + 1}", Modifier.width(Tokens.reader.pageNumberWidth), textAlign = TextAlign.End,
            style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace, color = Tokens.onSurface,
        )
        // The slider runs the way the pages do, so dragging toward the end of
        // a right-to-left chapter means dragging left.
        CompositionLocalProvider(LocalLayoutDirection provides if (rtl) LayoutDirection.Rtl else LayoutDirection.Ltr) {
            Slider(
                value = page.toFloat(),
                onValueChange = { onSeek(it.roundToInt()) },
                // A one-page chapter has nowhere to slide; an empty range would divide by zero.
                valueRange = 0f..maxOf(pageCount - 1, 1).toFloat(),
                enabled = pageCount > 1,
                colors = SliderDefaults.colors(
                    thumbColor = Tokens.primary,
                    activeTrackColor = Tokens.primary,
                    inactiveTrackColor = Tokens.outlineVariant,
                ),
                modifier = Modifier.weight(1f).semantics { contentDescription = "Page" },
            )
        }
        Text(
            "$pageCount", Modifier.width(Tokens.reader.pageNumberWidth),
            style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace, color = Tokens.onSurfaceVariant,
        )
    }
}

/** The web's ReaderSheet below xl: a bottom sheet, where a thumb reaches it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReaderSheet(title: String, onClose: () -> Unit, content: @Composable () -> Unit) {
    val window = LocalWindowInfo.current.containerSize
    val tallest = with(LocalDensity.current) { window.height.toDp() } * Tokens.reader.sheetMaxHeight
    ModalBottomSheet(
        onDismissRequest = onClose,
        sheetState = rememberBottomSheetState(SheetValue.Hidden, enabledValues = setOf(SheetValue.Hidden, SheetValue.Expanded)),
        shape = RoundedCornerShape(topStart = Tokens.radius.xl, topEnd = Tokens.radius.xl),
        containerColor = Tokens.surfaceContainer,
        scrimColor = Tokens.surfaceContainerLowest.copy(alpha = Tokens.reader.scrimAlpha),
        dragHandle = null,
    ) {
        Column(Modifier.heightIn(max = tallest)) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = Tokens.space.lg, vertical = Tokens.space.md),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(title, style = MaterialTheme.typography.titleLarge, color = Tokens.onSurface)
                GlyphButton("✕", "Close", onClose, Modifier.padding(Tokens.space.xs))
            }
            Box(Modifier.padding(start = Tokens.space.lg, end = Tokens.space.lg, bottom = Tokens.space.lg)) { content() }
        }
    }
}

private val modes = listOf(
    "paged_rtl" to "Paged (right to left)",
    "paged_ltr" to "Paged (left to right)",
    "double" to "Double page",
    "long_strip" to "Long strip",
)
private val scales = listOf("fit_screen" to "Fit screen", "fit_width" to "Fit width", "fit_height" to "Fit height")
private val backgrounds = listOf("black" to "Black", "gray" to "Gray", "white" to "White")

/** The web's SettingsPanel: Layout holds the mode, Image the scale and background. */
@Composable
internal fun SettingsSheet(prefs: ReaderPrefs, onChange: (ReaderPrefs) -> Unit, onClose: () -> Unit) {
    var tab by remember { mutableStateOf("layout") }
    // Two pages side by side are each a quarter of a phone: offered from a
    // tablet's width up. A series already set to it keeps the choice visible.
    val wide = currentWindowAdaptiveInfoV2().windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_MEDIUM_LOWER_BOUND)
    val offered = modes.filter { it.first != "double" || wide || prefs.mode == "double" }
    // Any choice made here is this series' own, as the web marks it.
    val change = { next: ReaderPrefs -> onChange(next.copy(custom = true)) }
    ReaderSheet("Reader settings", onClose) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            Tabs(listOf("layout" to "Layout", "image" to "Image"), tab) { tab = it }
            if (tab == "layout") {
                OptionGroup("Reading mode", offered, prefs.mode) { change(prefs.copy(mode = it)) }
            } else {
                OptionGroup("Scale", scales, prefs.scale) { change(prefs.copy(scale = it)) }
                OptionGroup("Background", backgrounds, prefs.background) { change(prefs.copy(background = it)) }
            }
            HorizontalDivider(Modifier.padding(top = Tokens.space.lg), color = Tokens.outlineVariant)
            Text(
                if (prefs.custom) "Saved for this series." else "Following the default for every series.",
                Modifier.padding(top = Tokens.space.md),
                style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun Tabs(options: List<Pair<String, String>>, value: String, onChange: (String) -> Unit) {
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
            options.forEach { (key, label) ->
                val selected = key == value
                // As wide as the label, so the underline is too.
                Column(
                    Modifier.width(IntrinsicSize.Max)
                        .clip(RoundedCornerShape(topStart = Tokens.radius.lg, topEnd = Tokens.radius.lg))
                        .clickable { onChange(key) },
                ) {
                    Text(
                        label,
                        Modifier.padding(horizontal = Tokens.space.md, vertical = Tokens.space.sm),
                        style = MaterialTheme.typography.labelMedium,
                        color = if (selected) Tokens.onSurface else Tokens.outline,
                    )
                    Box(
                        Modifier.fillMaxWidth().height(Tokens.reader.tabIndicator)
                            .background(if (selected) Tokens.primary else Color.Transparent),
                    )
                }
            }
        }
        HorizontalDivider(thickness = Tokens.reader.hairline, color = Tokens.outlineVariant)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun OptionGroup(label: String, options: List<Pair<String, String>>, value: String, onChange: (String) -> Unit) {
    Column(Modifier.padding(top = Tokens.space.md)) {
        Text(
            label, Modifier.padding(bottom = Tokens.space.sm),
            style = MaterialTheme.typography.labelMedium, color = Tokens.onSurfaceVariant,
        )
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
            verticalArrangement = Arrangement.spacedBy(Tokens.space.sm),
        ) {
            options.forEach { (key, text) ->
                val selected = key == value
                val shape = RoundedCornerShape(Tokens.radius.lg)
                Box(
                    Modifier.clip(shape)
                        .border(Tokens.reader.hairline, if (selected) Tokens.primary else Tokens.outlineVariant, shape)
                        .background(if (selected) Tokens.primary.copy(alpha = Tokens.reader.selectedAlpha) else Color.Transparent)
                        .clickable { onChange(key) }
                        .padding(horizontal = Tokens.space.md, vertical = Tokens.space.sm),
                ) {
                    Text(
                        text, style = MaterialTheme.typography.bodyMedium,
                        color = if (selected) Tokens.primary else Tokens.onSurface,
                    )
                }
            }
        }
    }
}

/**
 * The web's ChapterPanel. A chapter that cannot be read from here is drawn
 * dimmed and does nothing: opening it would only replace the page with the
 * reason.
 */
@Composable
internal fun ChapterSheet(ui: ReaderUi, onOpen: (Long) -> Unit, onClose: () -> Unit) {
    ReaderSheet("Chapters", onClose) {
        LazyColumn {
            items(ui.chapters, key = { it.id }) { row -> ChapterLine(row, row.id == ui.chapter.id, row.id in ui.readable, onOpen) }
        }
    }
}

@Composable
private fun ChapterLine(row: ChapterRow, current: Boolean, readable: Boolean, onOpen: (Long) -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(Tokens.radius.lg))
            .background(if (current) Tokens.primary.copy(alpha = Tokens.reader.selectedAlpha) else Color.Transparent)
            .clickable(enabled = readable) { onOpen(row.id) }
            .alpha(if (readable) 1f else Tokens.dimmed)
            .padding(Tokens.space.sm),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) {
        Text(
            "Ch. ${formatChapter(row.number)}", style = MaterialTheme.typography.labelMedium,
            fontFamily = FontFamily.Monospace, color = if (current) Tokens.primary else Tokens.onSurface,
        )
        Text(
            row.title.orEmpty(), Modifier.weight(1f), style = MaterialTheme.typography.bodySmall,
            color = Tokens.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis,
        )
        // Where the web says "streams": here a chapter is read from a file or not at all.
        if (!readable) {
            Text(
                if (row.availability == Availability.NotDownloaded) "not downloaded" else "not on device",
                style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace, color = Tokens.outline,
            )
        }
    }
}

/** Buttons as the web's: surface by default, primary for the one thing to do next. */
@Composable
internal fun ReaderButton(text: String, onClick: () -> Unit, primary: Boolean = false, glyph: String? = null) {
    Row(
        Modifier.clip(RoundedCornerShape(Tokens.radius.lg))
            .background(if (primary) Tokens.primary else Tokens.surfaceContainerHigh)
            .clickable(onClick = onClick)
            .padding(horizontal = Tokens.space.md, vertical = Tokens.space.sm),
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val color = if (primary) Tokens.onPrimary else Tokens.onSurface
        glyph?.let { Text(it, style = MaterialTheme.typography.labelLarge, color = color) }
        Text(text, style = MaterialTheme.typography.labelMedium, color = color)
    }
}

// The web's formatChapter: 12 not 12.0, and at most two decimals.
internal fun formatChapter(number: Double): String {
    if (number % 1.0 == 0.0) return number.toLong().toString()
    return ((number * 100).roundToInt() / 100.0).toString()
}
