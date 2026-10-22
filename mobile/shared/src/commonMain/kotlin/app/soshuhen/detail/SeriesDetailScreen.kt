package app.soshuhen.detail

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.ui.graphics.RectangleShape
import app.soshuhen.ui.Divider
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.api.Series
import app.soshuhen.api.SeriesMetadata
import app.soshuhen.core.Availability
import app.soshuhen.core.ChapterRow
import app.soshuhen.core.readableFrom
import app.soshuhen.core.unreadableReason
import app.soshuhen.ui.Badge
import app.soshuhen.ui.ButtonVariant
import app.soshuhen.ui.CoverImage
import app.soshuhen.ui.EmptyState
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.MonoLabel
import app.soshuhen.ui.NoticeBar
import app.soshuhen.ui.NoticeTone
import app.soshuhen.ui.ProgressBar
import app.soshuhen.ui.StatePill
import app.soshuhen.ui.Tag
import app.soshuhen.ui.Tone
import app.soshuhen.ui.WebButton
import app.soshuhen.ui.WebCard
import app.soshuhen.ui.WebGlyph
import app.soshuhen.ui.WebIcon
import app.soshuhen.ui.WebToggle
import app.soshuhen.ui.chapterNumber
import app.soshuhen.ui.day
import app.soshuhen.ui.relativeTime
import app.soshuhen.ui.seriesFormat
import app.soshuhen.ui.theme.Tokens
import app.soshuhen.ui.theme.mono
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * frontend/src/features/series/SeriesDetailPage.tsx for the parts the app
 * has: the hero, the Progress card, the chapter table, then the device's own
 * card where the web's aside keeps its download controls.
 */
@Composable
fun SeriesDetailScreen(
    model: SeriesDetailViewModel,
    coverUrl: String,
    // At home with the server found: decides which rows the reader will open.
    home: Boolean,
    onRead: (chapterId: Long, page: Int?, seriesTitle: String) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val prompt by model.unmarkPrompt.collectAsStateWithLifecycle()
    val notice by model.notice.collectAsStateWithLifecycle()
    prompt?.let { count ->
        // Keep them is the filled button and the one the system dismisses to:
        // the app deletes only what it was plainly told to.
        AlertDialog(
            onDismissRequest = model::dismissUnmark,
            containerColor = Tokens.surfaceContainer,
            shape = RoundedCornerShape(Tokens.radius.xl),
            title = { Text("Delete the $count chapters on this device too?", style = MaterialTheme.typography.headlineSmall, color = Tokens.onSurface) },
            confirmButton = { WebButton("Keep them", { model.unmark(deleteFiles = false) }, variant = ButtonVariant.Primary) },
            dismissButton = { WebButton("Delete", { model.unmark(deleteFiles = true) }, variant = ButtonVariant.Danger) },
        )
    }
    BoxWithConstraints(Modifier.fillMaxSize().background(Tokens.background).statusBarsPadding()) {
        val phone = maxWidth < Tokens.box.sm
        val wide = maxWidth >= Tokens.box.lg
        val side = if (phone) Tokens.space.lg else Tokens.space.margin
        when (val s = state) {
            LoadState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                LinearProgressIndicator(Modifier.width(Tokens.coverMinWidth), color = Tokens.primary)
            }
            is LoadState.Failed -> Box(Modifier.fillMaxSize().padding(side), Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
                    EmptyState(WebIcon.Warning, "Couldn't load this series", s.message)
                    WebButton("Retry", model::refresh, icon = WebIcon.Sync)
                }
            }
            is LoadState.Loaded -> {
                val ui = s.data
                var showAll by rememberSaveable { mutableStateOf(false) }
                val bounded = ui.rows.size > Tokens.box.previewRows && !showAll
                val rows = if (bounded) ui.rows.take(Tokens.box.previewRows) else ui.rows
                // Rows run newest first; next and last read are found in reading order.
                val ascending = ui.rows.asReversed()
                val next = ascending.firstOrNull { !it.read }?.id
                val lastRead = ascending.lastOrNull { it.read }?.id
                LazyColumn(
                    contentPadding = PaddingValues(start = side, end = side, top = Tokens.space.xl, bottom = Tokens.space.xxl),
                ) {
                    s.refreshFailed?.let {
                        item { NoticeBar(it, NoticeTone.Error, Modifier.padding(bottom = Tokens.space.xl)) { WebButton("Retry", model::refresh, small = true, icon = WebIcon.Sync) } }
                    }
                    notice?.let { item { NoticeBar(it, NoticeTone.Error, Modifier.padding(bottom = Tokens.space.xl)) } }
                    item { Hero(ui.series, ui.metadata, coverUrl, phone, wide) }
                    item {
                        ProgressCard(ui, home, onRead, wide = maxWidth >= Tokens.box.md, Modifier.padding(top = Tokens.space.xxl))
                    }
                    item { ChapterTabs(ui.rows.size, Modifier.padding(top = Tokens.space.xl, bottom = Tokens.space.lg)) }
                    if (ui.rows.isEmpty()) {
                        item {
                            Text(
                                "No chapters discovered yet.",
                                style = MaterialTheme.typography.bodySmall,
                                color = Tokens.onSurfaceVariant,
                                modifier = Modifier.fillMaxWidth()
                                    .background(Tokens.surfaceContainerLow, RoundedCornerShape(Tokens.radius.xl))
                                    .padding(Tokens.space.lg),
                            )
                        }
                    } else {
                        item { TableTop() }
                        itemsIndexed(rows, key = { _, row -> row.id }) { index, row ->
                            ChapterLine(
                                row,
                                last = index == rows.lastIndex,
                                isNext = row.id == next,
                                isLastRead = row.id == lastRead,
                                readable = readableFrom(row, home),
                                onRead = { onRead(row.id, 0, ui.series.title) },
                                onDelete = { model.deleteChapter(row.id) },
                            )
                        }
                    }
                    if (ui.rows.size > Tokens.box.previewRows) {
                        item {
                            Row(
                                Modifier.padding(top = Tokens.space.sm),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(Tokens.space.lg),
                            ) {
                                WebButton(
                                    if (showAll) "Show the last ${Tokens.box.previewRows}" else "Show all ${ui.rows.size} chapters",
                                    { showAll = !showAll },
                                    icon = WebIcon.Chevron,
                                )
                                if (bounded) MonoLabel("Showing the last ${Tokens.box.previewRows} of ${ui.rows.size}", modifier = Modifier.weight(1f, fill = false))
                            }
                        }
                    }
                    item { DeviceCard(ui, model, Modifier.padding(top = Tokens.space.xl)) }
                }
            }
        }
    }
}

// The library's arithmetic, repeated here because feature packages never import each other.
private fun totalChapters(s: Series): Int? = max(s.totalChapters ?: 0, s.known).takeIf { it > 0 }

private val PUBLICATION_LABEL = mapOf(
    "releasing" to "Publishing",
    "finished" to "Finished",
    "not_yet_released" to "Not yet published",
    "cancelled" to "Cancelled",
    "hiatus" to "On hiatus",
)

private val STATUS_LABEL = mapOf(
    "reading" to "Reading",
    "plan_to_read" to "Plan to read",
    "completed" to "Completed",
    "on_hold" to "On hold",
    "dropped" to "Dropped",
)

// frontend/src/lib/format.ts's STATUS_TONE.
private val STATUS_TONE = mapOf(
    "reading" to Tone.Secondary,
    "plan_to_read" to Tone.Primary,
    "completed" to Tone.Tertiary,
    "on_hold" to Tone.Warning,
    "dropped" to Tone.Error,
)

private fun runYears(start: Int?, end: Int?): String? = when {
    start == null || start == 0 -> null
    end == null || end == 0 -> "$start — present"
    end == start -> "$start"
    else -> "$start — $end"
}

/** The cover and SeriesHeader.tsx: badges, the title, credits and genres. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Hero(series: Series, metadata: SeriesMetadata, coverUrl: String, phone: Boolean, wide: Boolean) {
    val shape = RoundedCornerShape(Tokens.radius.xl)
    val cover = @Composable { modifier: Modifier ->
        CoverImage(coverUrl, series.title, modifier.shadow(Tokens.cardElevation, shape, clip = false), shape = shape)
    }
    val header = @Composable { modifier: Modifier ->
        Column(modifier, verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
            metadata.publisher?.let { MonoLabel(it, uppercase = true) }
            val format = seriesFormat(series.format)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm), verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                metadata.publicationStatus?.let { status -> PUBLICATION_LABEL[status]?.let { Badge(it, Tone.Secondary) } }
                runYears(metadata.startYear, metadata.endYear)?.let { Badge(it, Tone.Tertiary) }
                metadata.demographic?.let { Badge(it, Tone.Primary) }
                metadata.country?.let { Tag(it) }
                format?.let { Badge(it, Tone.Tertiary) }
                series.status?.let { status -> StatePill(STATUS_LABEL[status] ?: status, STATUS_TONE[status] ?: Tone.Primary) }
                if (series.state == "needs_review") Badge("Needs review", Tone.Error)
                if (series.autoDownload) Badge("Auto-download active", Tone.Secondary)
            }
            Text(series.title, style = MaterialTheme.typography.displayLarge, color = Tokens.onSurface)
            metadata.nativeTitle?.takeIf { it != series.title }?.let {
                Text(it, style = MaterialTheme.typography.headlineMedium, color = Tokens.onSurfaceVariant)
            }
            if (metadata.credits.isNotEmpty()) {
                Text(
                    buildAnnotatedString {
                        metadata.credits.take(3).forEachIndexed { index, credit ->
                            if (index > 0) append(" · ")
                            append("${credit.role} by ")
                            withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = Tokens.onSurface)) { append(credit.name) }
                        }
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = Tokens.onSurfaceVariant,
                )
            }
            if (series.genres.isNotEmpty()) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(Tokens.space.xsPlus), verticalArrangement = Arrangement.spacedBy(Tokens.space.xsPlus)) {
                    series.genres.forEach { Tag(it) }
                }
            }
        }
    }
    if (wide) {
        // lg:grid-cols-12 with the cover on three.
        Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.xxl)) {
            cover(Modifier.weight(3f))
            header(Modifier.weight(9f))
        }
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.xxl)) {
            cover(Modifier.width(if (phone) Tokens.box.heroCover else Tokens.box.heroCoverWide))
            header(Modifier.fillMaxWidth())
        }
    }
}

/** ProgressManager.tsx's card, read only: the app records progress by reading, not by typing it. */
@Composable
private fun ProgressCard(
    ui: DetailUi,
    home: Boolean,
    onRead: (chapterId: Long, page: Int?, seriesTitle: String) -> Unit,
    wide: Boolean,
    modifier: Modifier = Modifier,
) {
    val series = ui.series
    val total = totalChapters(series)
    val remaining = total?.let { max(it - series.progress, 0) }
    val estimate = if (remaining != null && ui.minutesPerChapter != null) remaining * ui.minutesPerChapter else null
    WebCard(modifier.fillMaxWidth(), spacing = Tokens.space.xl) {
        Text("Progress", style = MaterialTheme.typography.headlineSmall, color = Tokens.onSurface)
        val chapters = @Composable { inner: Modifier ->
            Column(inner, verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                MonoLabel("Chapters read", uppercase = true)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                    Text(
                        chapterNumber(series.progress.toDouble()),
                        style = MaterialTheme.typography.headlineLarge,
                        color = Tokens.onSurface,
                        modifier = Modifier.background(Tokens.surfaceContainerHigh, RoundedCornerShape(Tokens.radius.lg))
                            .padding(horizontal = Tokens.space.lg),
                    )
                    total?.let { Text("/ $it", style = MaterialTheme.typography.labelMedium.mono(), color = Tokens.outline) }
                }
                total?.let { ProgressBar(series.progress.toFloat(), it.toFloat()) }
                remaining?.let {
                    // Labelled an estimate because it is derived from a setting, not measured.
                    MonoLabel("$it chapters left" + (estimate?.let { minutes -> " · about ${(minutes / 60f).roundToInt()}h estimated" } ?: ""))
                }
                ui.continueWith?.let { next ->
                    // Still the resume chapter, as on the web: that is where the
                    // user is. Dimmed like the rows when the reader would refuse it,
                    // and still tappable, with the reason said here first.
                    val reason = unreadableReason(next, home)
                    WebButton(
                        "Continue chapter ${chapterNumber(next.number)}",
                        { onRead(next.id, ui.continuePage, series.title) },
                        Modifier.padding(top = Tokens.space.sm).alpha(if (reason == null) 1f else Tokens.dimmed),
                        variant = ButtonVariant.Primary,
                        icon = WebIcon.Book,
                    )
                    reason?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant) }
                }
            }
        }
        val facts = @Composable { inner: Modifier ->
            val m = ui.metadata
            Column(inner, verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                m.volumesTotal?.let { Fact("Volumes", if (m.volumesRead != null) "${m.volumesRead} of $it" else "$it in total") }
                m.startedAt?.let { Fact("Started", day(it)) }
                m.completedAt?.let { Fact("Finished", day(it)) }
                m.listUpdatedAt?.let { Fact("Last updated", relativeTime(it)) }
                m.rereadCount?.let { Fact("Rereads", "$it") }
            }
        }
        if (wide) {
            Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.xl)) {
                chapters(Modifier.weight(1f))
                facts(Modifier.weight(1f))
            }
        } else {
            chapters(Modifier.fillMaxWidth())
            facts(Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun Fact(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
        MonoLabel(label, modifier = Modifier.weight(1f))
        Text(value, style = MaterialTheme.typography.labelMedium.mono(), color = Tokens.onSurface)
    }
}

/** Tabs.tsx with the one tab the app has: its label over a primary underline, on the strip's rule. */
@Composable
private fun ChapterTabs(count: Int, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth()) {
        Column(Modifier.width(IntrinsicSize.Max)) {
            Row(
                Modifier.padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs),
            ) {
                Text("Chapters", style = MaterialTheme.typography.labelMedium, color = Tokens.onSurface)
                MonoLabel("($count)")
            }
            Box(Modifier.fillMaxWidth().height(Tokens.reader.tabIndicator).background(Tokens.primary))
        }
        Divider(color = Tokens.outlineVariant)
    }
}

private val tableShape = RoundedCornerShape(topStart = Tokens.radius.xl, topEnd = Tokens.radius.xl)
private val tableEnd = RoundedCornerShape(bottomStart = Tokens.radius.xl, bottomEnd = Tokens.radius.xl)

/** ChapterTable.tsx's header row, the top of its rounded surface-container-low table. */
@Composable
private fun TableTop() {
    Column(Modifier.fillMaxWidth().background(Tokens.surfaceContainerLow, tableShape)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm)) {
            MonoLabel("Chapter", modifier = Modifier.weight(1f))
            MonoLabel("State", modifier = Modifier.padding(end = Tokens.space.xl))
            MonoLabel("Read")
        }
        Divider(color = Tokens.surfaceContainerHighest.copy(alpha = Tokens.ruleAlpha))
    }
}

// ChapterTable.tsx's own words and tones for the server's chapter states.
private val STATE_LABEL = mapOf(
    "downloaded" to "Downloaded",
    "downloading" to "Downloading",
    "queued" to "Queued",
    "known" to "Known",
    "failed" to "Failed",
    "skipped" to "Skipped",
)
private val STATE_TONE = mapOf(
    "downloaded" to Tone.Secondary,
    "downloading" to Tone.Tertiary,
    "queued" to Tone.Tertiary,
    "known" to Tone.Primary,
    "failed" to Tone.Error,
    "skipped" to Tone.Primary,
)

@Composable
private fun ChapterLine(
    row: ChapterRow,
    last: Boolean,
    isNext: Boolean,
    isLastRead: Boolean,
    readable: Boolean,
    onRead: () -> Unit,
    onDelete: () -> Unit,
) {
    Column(
        Modifier.fillMaxWidth()
            .background(Tokens.surfaceContainerLow, if (last) tableEnd else RectangleShape)
            .clip(if (last) tableEnd else RectangleShape)
            // Still tappable when the reader would refuse it: the reader says why.
            .clickable(onClick = onRead),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm)
                .alpha(if (readable) 1f else Tokens.dimmed),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
        ) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                    Text(
                        "Ch ${chapterNumber(row.number)}",
                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
                        color = if (row.read) Tokens.secondary else Tokens.onSurface,
                    )
                    if (isLastRead) WebGlyph(WebIcon.Bookmark, Tokens.tertiary, Tokens.icon.sm)
                    if (isNext) {
                        MonoLabel(
                            "Next",
                            Tokens.primary,
                            Modifier.background(Tokens.primary.copy(alpha = Tokens.tintAlpha), CircleShape)
                                .padding(horizontal = Tokens.space.sm, vertical = Tokens.space.xxs),
                        )
                    }
                }
                row.title?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.labelSmall.mono(),
                        color = if (row.read) Tokens.secondary.copy(alpha = Tokens.readTitleAlpha) else Tokens.outline,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            if (row.availability == Availability.OnDevice) {
                StatePill("On device", Tone.Secondary)
            } else {
                val state = row.state ?: if (row.availability == Availability.OnServer) "downloaded" else "known"
                StatePill(STATE_LABEL[state] ?: state, STATE_TONE[state] ?: Tone.Primary)
            }
            if (row.availability == Availability.OnDevice) {
                WebButton("Delete", onDelete, variant = ButtonVariant.Danger, small = true)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.xsPlus)) {
                WebGlyph(WebIcon.Book, Tokens.primary, Tokens.icon.sm)
                MonoLabel("Read", Tokens.primary)
            }
        }
        if (!last) Divider(color = Tokens.surfaceContainerHighest.copy(alpha = Tokens.rowRuleAlpha))
    }
}

/** The device's own card, where the web's aside keeps DownloadControls. */
@Composable
private fun DeviceCard(ui: DetailUi, model: SeriesDetailViewModel, modifier: Modifier = Modifier) {
    WebCard(modifier.fillMaxWidth(), spacing = Tokens.space.sm) {
        Text("On this device", style = MaterialTheme.typography.titleMedium, color = Tokens.onSurface)
        WebToggle("Keep on this device", ui.marked, model::setMarked)
        Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
            Divider(color = Tokens.surfaceContainerHighest.copy(alpha = Tokens.ruleAlpha))
            MonoLabel(
                "${ui.deviceChapters} chapter${if (ui.deviceChapters == 1) "" else "s"} on this device",
                Tokens.onSurfaceVariant,
                Modifier.padding(top = Tokens.space.sm),
            )
            WebButton("Delete read chapters", model::deleteRead, variant = ButtonVariant.Danger, small = true, enabled = ui.readOnDevice > 0)
        }
    }
}
