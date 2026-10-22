package app.soshuhen.updates

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.style.TextOverflow
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.core.LocalStore
import app.soshuhen.core.newChaptersText
import app.soshuhen.ui.CoverImage
import app.soshuhen.ui.Divider
import app.soshuhen.ui.EmptyState
import app.soshuhen.ui.MonoLabel
import app.soshuhen.ui.ProblemBanner
import app.soshuhen.ui.SectionHeader
import app.soshuhen.ui.WebIcon
import app.soshuhen.ui.relativeTime
import app.soshuhen.ui.theme.Tokens

/**
 * What the background copy brought in, newest first, a card per day. The
 * rows are the web's notification panel (app/NotificationBell.tsx) and the
 * page around them is SettingsPage's section style.
 */
@Composable
fun UpdatesScreen(
    model: UpdatesViewModel,
    store: LocalStore,
    coverUrl: (Long) -> String,
    onOpen: (Long) -> Unit,
) {
    val rows by model.rows.collectAsStateWithLifecycle()
    BoxWithConstraints(Modifier.fillMaxSize().background(Tokens.background).statusBarsPadding()) {
        val side = if (maxWidth < Tokens.box.sm) Tokens.space.lg else Tokens.space.margin
        LazyColumn(
            Modifier.fillMaxHeight().fillMaxWidth().widthIn(max = Tokens.canvasMaxWidth).align(Alignment.TopCenter),
            contentPadding = PaddingValues(start = side, end = side, top = Tokens.space.xl, bottom = Tokens.space.xxl),
            verticalArrangement = Arrangement.spacedBy(Tokens.space.lg),
        ) {
            item {
                SectionHeader(WebIcon.Bell, "Updates", "New chapters copied to this device")
            }
            item { ProblemBanner(store) }
            if (rows.isEmpty()) {
                item { EmptyState(WebIcon.Bell, "No updates yet", "New chapters copied to this device show up here.") }
            }
            rows.groupBy { it.day }.forEach { (day, group) ->
                item(key = "day-$day") { DayCard(day, group, coverUrl, onOpen) }
            }
        }
    }
}

/** The notification panel's card: a title-md header over its rows. */
@Composable
private fun DayCard(day: String, rows: List<ImportLogRow>, coverUrl: (Long) -> String, onOpen: (Long) -> Unit) {
    val shape = RoundedCornerShape(Tokens.radius.xl)
    Column(
        Modifier.fillMaxWidth()
            .shadow(Tokens.cardElevation, shape, clip = false)
            .background(Tokens.surfaceContainer, shape),
    ) {
        Text(
            day,
            style = MaterialTheme.typography.titleMedium,
            color = Tokens.onSurface,
            modifier = Modifier.padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm),
        )
        Divider()
        Column(Modifier.padding(vertical = Tokens.space.xs)) {
            rows.forEach { row -> UpdateRow(row, coverUrl(row.seriesId), onOpen) }
        }
    }
}

@Composable
private fun UpdateRow(row: ImportLogRow, coverUrl: String, onOpen: (Long) -> Unit) {
    val (title, text) = newChaptersText(row.seriesTitle, listOf(row.number))
    Row(
        Modifier.fillMaxWidth().clickable { onOpen(row.seriesId) }
            .padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm),
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CoverImage(coverUrl, row.seriesTitle, Modifier.size(Tokens.thumbWidth, Tokens.box.thumbHeight), fill = true)
        Column(Modifier.weight(1f)) {
            Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium, color = Tokens.onSurface)
            Text(text, color = Tokens.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            MonoLabel(relativeTime(row.importedAt))
        }
    }
}
