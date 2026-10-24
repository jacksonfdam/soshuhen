package app.soshuhen.library

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.ui.unit.Dp
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.api.Series
import app.soshuhen.core.LocalStore
import app.soshuhen.ui.CoverImage
import app.soshuhen.ui.EmptyState
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.MonoLabel
import app.soshuhen.ui.NoticeBar
import app.soshuhen.ui.NoticeTone
import app.soshuhen.ui.ProblemBanner
import app.soshuhen.ui.Tone
import app.soshuhen.ui.WebButton
import app.soshuhen.ui.WebChip
import app.soshuhen.ui.WebGlyph
import app.soshuhen.ui.WebIcon
import app.soshuhen.ui.chapterNumber
import app.soshuhen.ui.providers
import app.soshuhen.ui.relativeTime
import app.soshuhen.ui.seriesFormat
import app.soshuhen.ui.theme.Tokens
import app.soshuhen.ui.theme.mono
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

const val NOT_ON_DEVICE = "Not on this device. Mark it at home to read it here."

/**
 * The library as frontend/src/features/library/LibraryPage.tsx lays it out:
 * the status tabs on their panel, the filter panel, Continue reading, then the
 * cover grid under a heading that counts what is shown.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(
    model: LibraryViewModel,
    store: LocalStore,
    coverUrl: (Long) -> String,
    onOpen: (Long) -> Unit,
    // Pull-to-refresh also asks the background copy to run, so a chapter the
    // server just finished arrives without waiting for the hour.
    onRefreshed: () -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val status by model.status.collectAsStateWithLifecycle()
    val query by model.query.collectAsStateWithLifecycle()
    val marked by model.marked.collectAsStateWithLifecycle()
    val onDevice by model.onDevice.collectAsStateWithLifecycle()
    val atHome by model.atHome.collectAsStateWithLifecycle()
    var notice by remember { mutableStateOf<String?>(null) }
    // One rule for the grid and the continue row, so neither opens what the
    // device cannot show.
    val open = { series: Series ->
        if (reachable(series, atHome, marked)) {
            notice = null
            onOpen(series.id)
        } else {
            notice = NOT_ON_DEVICE
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize().background(Tokens.background).statusBarsPadding()) {
        // The web pads by space-md on a phone and by margin from sm up.
        val phone = maxWidth < Tokens.box.sm
        val pane = maxWidth
        val side = if (phone) Tokens.space.lg else Tokens.space.margin
        Column(Modifier.fillMaxSize()) {
            ProblemBanner(store, Modifier.padding(horizontal = side, vertical = Tokens.space.sm))
            Box(Modifier.weight(1f)) {
                when (val s = state) {
                    LoadState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                        LinearProgressIndicator(Modifier.width(Tokens.coverMinWidth), color = Tokens.primary)
                    }
                    is LoadState.Failed -> Box(Modifier.fillMaxSize().padding(side), Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
                            EmptyState(WebIcon.Warning, "Couldn't load the library", s.message)
                            WebButton("Retry", model::refresh, icon = WebIcon.Sync)
                        }
                    }
                    is LoadState.Loaded -> PullToRefreshBox(isRefreshing = false, onRefresh = { model.refresh(); onRefreshed() }) {
                        val all = s.data
                        val shown = visible(all, status, query, marked)
                        // AppShell's canvas: the page fills the pane up to its max and is centred past it.
                        val content = minOf(pane, Tokens.canvasMaxWidth + side * 2) - side * 2
                        val cells = gridCells(content, phone)
                        LazyColumn(
                            contentPadding = PaddingValues(start = side, end = side, top = Tokens.space.xl, bottom = Tokens.space.xxl),
                            verticalArrangement = Arrangement.spacedBy(Tokens.space.gutter),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            modifier = Modifier.fillMaxSize(),
                        ) {
                            val page = Modifier.width(content)
                            s.refreshFailed?.let { message ->
                                item {
                                    NoticeBar(message, NoticeTone.Error, page) { WebButton("Retry", model::refresh, small = true, icon = WebIcon.Sync) }
                                }
                            }
                            notice?.let { message -> item { NoticeBar(message, modifier = page) } }
                            item { StatusPanel(all, marked, status, model::setStatus, page) }
                            item { FilterPanel(query, model::setQuery, page) }
                            val continuing = continueReading(all)
                            if (continuing.isNotEmpty()) {
                                item {
                                    ContinueReading(continuing, coverUrl, { reachable(it, atHome, marked) }, open, threeUp = pane >= Tokens.box.md, page.padding(top = Tokens.space.gutter))
                                }
                            }
                            item {
                                Heading(status, shown.size, all.size, page.padding(top = Tokens.space.gutter))
                            }
                            if (shown.isEmpty()) {
                                item {
                                    EmptyState(
                                        WebIcon.Search,
                                        "No matches",
                                        "Nothing in this status matches the current filter. Try another tab or clear the search.",
                                        page,
                                    )
                                }
                            }
                            // Rows laid out by hand rather than a lazy grid: a grid's
                            // full-width items are only as wide as its columns, which
                            // left the panels above short of the page's right edge.
                            items(shown.chunked(cells.count), key = { row -> row.first().id }) { row ->
                                Row(page, horizontalArrangement = Arrangement.spacedBy(Tokens.space.gutter)) {
                                    row.forEach { series ->
                                        CoverCard(
                                            series, coverUrl(series.id), dimmed = !reachable(series, atHome, marked),
                                            onDevice = series.id in onDevice,
                                            Modifier.width(cells.width),
                                        ) { open(series) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private class Cells(val count: Int, val width: Dp)

/**
 * SeriesGrid.tsx: two columns on a phone, then auto-fill minmax(160px, 220px)
 * from sm, so the columns stop at 220 and leave the rest of the row empty
 * instead of stretching the covers. The 160 floor never binds: a pane too
 * narrow for one 220 column is a phone, which takes the two-column branch.
 */
private fun gridCells(available: Dp, phone: Boolean): Cells {
    val gap = Tokens.space.gutter
    if (phone) return Cells(2, (available - gap) / 2)
    // CSS counts auto-fill repetitions by the track's max when it has one,
    // then lets each track grow no further than that max.
    val most = Tokens.box.gridMax
    val count = max(1, ((available + gap) / (most + gap)).toInt())
    return Cells(count, minOf(most, (available - gap * (count - 1)) / count))
}

/** StatusTabs.tsx on LibraryPage's rounded-2xl panel: every status, then the device, then All last. */
@Composable
private fun StatusPanel(all: List<Series>, marked: Set<Long>, status: String?, onChange: (String?) -> Unit, modifier: Modifier) {
    val shape = RoundedCornerShape(Tokens.radius.lg)
    Row(
        modifier
            .shadow(Tokens.cardElevation, shape, clip = false)
            .background(Tokens.surfaceContainerLow, shape)
            .padding(Tokens.space.sm)
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs),
    ) {
        STATUS_ORDER.forEach { key ->
            WebChip(STATUS_LABEL.getValue(key), all.count { it.status == key }, status == key) { onChange(key) }
        }
        WebChip("On device", all.count { it.id in marked }, status == ON_DEVICE) { onChange(ON_DEVICE) }
        WebChip("All", all.size, status == null) { onChange(null) }
    }
}

/** The filter panel's SearchField (ListControls.tsx). */
@Composable
private fun FilterPanel(query: String, onQuery: (String) -> Unit, modifier: Modifier) {
    Box(
        modifier
            .background(Tokens.surfaceContainer.copy(alpha = Tokens.filterPanelAlpha), RoundedCornerShape(Tokens.radius.xl))
            .padding(Tokens.space.mdPlus),
    ) {
        BasicTextField(
            value = query,
            onValueChange = onQuery,
            singleLine = true,
            textStyle = MaterialTheme.typography.bodySmall.copy(color = Tokens.onSurface),
            cursorBrush = SolidColor(Tokens.primary),
            modifier = Modifier.fillMaxWidth(),
            decorationBox = { field ->
                Row(
                    Modifier.fillMaxWidth()
                        .background(Tokens.surfaceContainerLow, RoundedCornerShape(Tokens.radius.lg))
                        .padding(horizontal = Tokens.space.md, vertical = Tokens.space.sm),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
                ) {
                    WebGlyph(WebIcon.Search, Tokens.outline)
                    Box(Modifier.weight(1f)) {
                        if (query.isEmpty()) Text("Filter by title...", style = MaterialTheme.typography.bodySmall, color = Tokens.outline)
                        field()
                    }
                }
            },
        )
    }
}

/** ContinueReading.tsx: one column on a phone, three from md. */
@Composable
private fun ContinueReading(
    series: List<Series>,
    coverUrl: (Long) -> String,
    isReachable: (Series) -> Boolean,
    onOpen: (Series) -> Unit,
    // md: is the window's width on the web, not the section's, so a page
    // inset by its margins still goes three-up at 768.
    threeUp: Boolean,
    modifier: Modifier = Modifier,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.smPlus)) {
            WebGlyph(WebIcon.Sparkle, Tokens.primary, Tokens.icon.lg)
            Text("Continue reading", style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold), color = Tokens.onSurface)
            Text(
                "Instant access",
                style = MaterialTheme.typography.labelSmall.mono(),
                color = Tokens.outline,
                modifier = Modifier.background(Tokens.surfaceContainerHigh, RoundedCornerShape(Tokens.radius.base))
                    .padding(horizontal = Tokens.space.sm, vertical = Tokens.space.xxs),
            )
        }
        if (!threeUp) {
            Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
                series.forEach { ContinueCard(it, coverUrl(it.id), isReachable(it), onOpen, Modifier.fillMaxWidth()) }
            }
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
                series.forEach { ContinueCard(it, coverUrl(it.id), isReachable(it), onOpen, Modifier.weight(1f)) }
                // Three slots whatever the count, as the web's grid-cols-3 keeps them.
                repeat(3 - series.size) { Box(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun ContinueCard(row: Series, coverUrl: String, reachable: Boolean, onOpen: (Series) -> Unit, modifier: Modifier) {
    val total = totalChapters(row)
    val extra = unread(row)
    val shape = RoundedCornerShape(Tokens.radius.xl)
    Row(
        modifier
            .alpha(if (reachable) 1f else Tokens.dimmed)
            .shadow(Tokens.cardElevation, shape, clip = false)
            .clip(shape)
            .background(Tokens.surfaceContainerLow)
            .clickable { onOpen(row) }
            .padding(Tokens.space.lg),
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.lg),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(Tokens.box.continueCoverWidth, Tokens.box.continueCoverHeight)) {
            CoverImage(coverUrl, row.title, Modifier.fillMaxSize(), shape = RoundedCornerShape(Tokens.radius.lg), fill = true)
            coverFormat(row)?.let { OverlayBadge(it, Tokens.onSurfaceVariant, Modifier.padding(Tokens.space.xs)) }
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Tokens.space.xxs)) {
            Row(Modifier.fillMaxWidth()) {
                // Three-up on a tablet the line cannot hold both; the web lets the
                // time overflow the card. Here the count keeps its words and the
                // time gives way: "21…" told the reader nothing.
                MonoLabel(
                    when {
                        total == null -> "Reading"
                        extra > 0 -> "$extra new chapter${if (extra == 1) "" else "s"}"
                        else -> "Up to date"
                    },
                    if (extra > 0) Tokens.secondary else Tokens.outline,
                )
                // Measured after the count, so it is the one that gives way.
                Box(Modifier.weight(1f))
                row.updatedAt?.let { MonoLabel(relativeTime(it), modifier = Modifier.padding(start = Tokens.space.xs)) }
            }
            Text(
                row.title,
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                color = Tokens.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(chapterOf(row.progress, total), style = MaterialTheme.typography.labelMedium.mono(), color = Tokens.onSurfaceVariant)
        }
    }
}

@Composable
private fun chapterOf(progress: Int, total: Int?) = buildAnnotatedString {
    append("Ch $progress")
    if (total != null) withStyle(SpanStyle(color = Tokens.outline)) { append(" / $total") }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Heading(status: String?, shown: Int, total: Int, modifier: Modifier = Modifier) {
    val title = when (status) {
        null -> "All series"
        "reading" -> "Active reading"
        ON_DEVICE -> "On this device"
        else -> "${STATUS_LABEL.getValue(status)} series"
    }
    // The web's flex-wrap items-baseline: the count moves under the title as one
    // line when the two do not fit side by side, rather than breaking mid-phrase.
    FlowRow(
        modifier,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
        itemVerticalAlignment = Alignment.Bottom,
    ) {
        Text(
            title,
            style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.ExtraBold),
            color = Tokens.onSurface,
            modifier = Modifier.alignByBaseline(),
        )
        // The app has no pages, so what is shown is what matched.
        Text(
            "Showing $shown of $shown matching · $total in the library",
            style = MaterialTheme.typography.labelMedium.mono(),
            color = Tokens.outline,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.alignByBaseline(),
        )
    }
}

/** The rounded badge the web lays over a cover (bg-surface-container-lowest/85). */
@Composable
private fun OverlayBadge(text: String, color: androidx.compose.ui.graphics.Color, modifier: Modifier = Modifier, background: androidx.compose.ui.graphics.Color = Tokens.surfaceContainerLowest.copy(alpha = Tokens.overlayAlpha), bold: Boolean = true) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall.mono().let { if (bold) it.copy(fontWeight = FontWeight.Bold) else it },
        color = color,
        maxLines = 2,
        overflow = TextOverflow.Ellipsis,
        modifier = modifier.background(background, RoundedCornerShape(Tokens.radius.base))
            .padding(horizontal = Tokens.space.xsPlus, vertical = Tokens.space.xxs),
    )
}

/**
 * The ⬇ on a cover whose archives are on the device, in OverlayBadge's frame.
 * The web has no such badge; the arrow is its Download glyph, so it reads as
 * the same family as the pipeline note's.
 */
@Composable
private fun DeviceBadge() {
    Box(
        Modifier.background(Tokens.surfaceContainerLowest.copy(alpha = Tokens.overlayAlpha), RoundedCornerShape(Tokens.radius.base))
            .padding(horizontal = Tokens.space.xsPlus, vertical = Tokens.space.xxs),
    ) {
        WebGlyph(WebIcon.Download, Tokens.secondary, Tokens.icon.sm)
    }
}

private class Note(val text: String, val icon: WebIcon, val tone: androidx.compose.ui.graphics.Color)

// CoverCard.tsx's pipelineNote, for the signals the app reads: a real one or none.
private fun pipelineNote(series: Series): Note? = when {
    series.state == "needs_review" -> Note("Needs a source mapping", WebIcon.Warning, Tokens.error)
    series.autoDownload -> Note("Auto-download active", WebIcon.Download, Tokens.secondary)
    series.downloaded > 0 -> Note("${series.downloaded} chapters downloaded", WebIcon.Check, Tokens.outline)
    series.sourceSite != null -> Note("Mapped to ${series.sourceSite}", WebIcon.Sync, Tokens.primary)
    else -> null
}

/** CoverCard.tsx: the art with its badges and progress strip, then the lines under it. */
@Composable
private fun CoverCard(series: Series, coverUrl: String, dimmed: Boolean, onDevice: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val total = totalChapters(series)
    val pct = total?.let { min(100, (series.progress * 100f / it).roundToInt()) }
    val format = coverFormat(series)
    val genre = series.genres.firstOrNull()
    val needsReview = series.state == "needs_review"
    val extra = unread(series)
    val shape = RoundedCornerShape(Tokens.radius.lg)
    Column(modifier.alpha(if (dimmed) Tokens.dimmed else 1f).clickable(onClick = onClick)) {
        Box(
            Modifier.fillMaxWidth().clip(shape)
                .border(Tokens.hairline, if (needsReview) Tokens.error.copy(alpha = Tokens.reviewBorderAlpha) else Tokens.coverEdge, shape),
        ) {
            CoverImage(coverUrl, series.title, Modifier.fillMaxWidth(), shape = shape)
            Column(Modifier.fillMaxWidth().padding(Tokens.space.sm), verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    when {
                        needsReview -> OverlayBadge("Needs review", Tokens.error, background = Tokens.errorContainer.copy(alpha = Tokens.reviewAlpha))
                        format != null -> OverlayBadge(format, Tokens.onSurfaceVariant)
                        else -> Box(Modifier)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                        series.score?.let { OverlayBadge("★ ${(kotlin.math.round(it * 10) / 10)}", Tokens.tertiary) }
                        if (onDevice) DeviceBadge()
                    }
                }
                if (series.providers.isNotEmpty()) {
                    OverlayBadge("${providers(series.providers)} sync", Tokens.primary, bold = false)
                }
            }
            // 4px, flush with the image's bottom edge, as DESIGN.md's cover card has it.
            Box(Modifier.align(Alignment.BottomStart).fillMaxWidth().height(Tokens.box.bar).background(Tokens.surfaceContainerLowest)) {
                Box(Modifier.fillMaxHeight().fillMaxWidth((pct ?: 0) / 100f).background(Tokens.secondary))
            }
        }
        Column(
            Modifier.padding(top = Tokens.space.smPlus, bottom = Tokens.space.sm),
            verticalArrangement = Arrangement.spacedBy(Tokens.space.xs),
        ) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    listOfNotNull(format, genre).joinToString(" • ").ifEmpty { " " },
                    style = MaterialTheme.typography.bodySmall.mono(),
                    color = Tokens.outline,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                pct?.let {
                    Text("$it%", style = MaterialTheme.typography.bodySmall.mono(), color = if (it >= 80) Tokens.secondary else Tokens.primary)
                }
            }
            Text(
                series.title,
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                color = Tokens.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            pipelineNote(series)?.let { note ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.xsPlus)) {
                    WebGlyph(note.icon, note.tone, Tokens.icon.xs)
                    MonoLabel(note.text, note.tone)
                }
            }
            Column {
                Box(Modifier.fillMaxWidth().height(Tokens.hairline).background(Tokens.surfaceContainerHighest.copy(alpha = Tokens.ruleAlpha)))
                Row(
                    Modifier.fillMaxWidth().padding(top = Tokens.space.xsPlus),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(chapterOf(series.progress, total), style = MaterialTheme.typography.bodySmall.mono(), color = Tokens.onSurface)
                    if (extra > 0) {
                        Text("+$extra new", style = MaterialTheme.typography.bodySmall.mono(), color = Tokens.secondary)
                    } else if (total != null) {
                        WebGlyph(WebIcon.Check, Tokens.secondary)
                    }
                }
            }
        }
    }
}
