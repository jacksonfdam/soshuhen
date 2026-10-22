package app.soshuhen.detail

import app.soshuhen.core.Availability
import app.soshuhen.core.readableFrom
import app.soshuhen.core.unreadableReason
import androidx.compose.foundation.clickable
import androidx.compose.ui.draw.alpha
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Switch
import androidx.compose.material3.TextButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.ui.CoverImage
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.theme.Tokens

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
            title = { Text("Delete the $count chapters on this device too?") },
            confirmButton = { Button(onClick = { model.unmark(deleteFiles = false) }) { Text("Keep them") } },
            dismissButton = { TextButton(onClick = { model.unmark(deleteFiles = true) }) { Text("Delete") } },
        )
    }
    when (val s = state) {
        LoadState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
            LinearProgressIndicator(Modifier.width(Tokens.coverMinWidth))
        }
        is LoadState.Failed -> Column(
            Modifier.fillMaxSize().padding(Tokens.space.xl),
            verticalArrangement = Arrangement.spacedBy(Tokens.space.md, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(s.message)
            Button(onClick = model::refresh) { Text("Retry") }
        }
        is LoadState.Loaded -> {
            val ui = s.data
            LazyColumn(contentPadding = PaddingValues(Tokens.space.lg), verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                s.refreshFailed?.let { item { Text(it, color = Tokens.warning) } }
                notice?.let { item { Text(it, color = Tokens.warning) } }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
                        CoverImage(coverUrl, ui.series.title, Modifier.width(Tokens.coverMinWidth))
                        Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                            Text(ui.series.title, style = MaterialTheme.typography.headlineSmall)
                            Text(
                                "Read up to chapter ${ui.series.progress} · ${ui.series.downloaded} on the server",
                                color = Tokens.onSurfaceVariant,
                            )
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                                Switch(checked = ui.marked, onCheckedChange = model::setMarked)
                                Text("Keep on this device")
                            }
                            TextButton(onClick = model::deleteRead, enabled = ui.readOnDevice > 0) { Text("Delete read chapters") }
                            ui.continueWith?.let { next ->
                                // Still the resume chapter, as on the web: that is where the
                                // user is. Dimmed like the rows when the reader would refuse it,
                                // and still tappable, with the reason said here first.
                                val reason = unreadableReason(next, home)
                                Button(
                                    onClick = { onRead(next.id, ui.continuePage, ui.series.title) },
                                    modifier = Modifier.alpha(if (reason == null) 1f else Tokens.dimmed),
                                ) {
                                    Text("Continue chapter ${formatNumber(next.number)}")
                                }
                                reason?.let {
                                    Text(it, style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
                items(ui.rows, key = { it.id }) { row ->
                    // Still tappable: the reader says why it cannot open the chapter.
                    Column(
                        Modifier
                            .clickable { onRead(row.id, 0, ui.series.title) }
                            .alpha(if (readableFrom(row, home)) 1f else Tokens.dimmed),
                    ) {
                        Row(
                            Modifier.fillMaxWidth().padding(vertical = Tokens.space.sm),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                "Chapter ${formatNumber(row.number)}" + (row.title?.let { " · $it" } ?: "") + if (row.read) "  ✓" else "",
                                color = if (row.read) Tokens.onSurfaceVariant else Tokens.onSurface,
                                modifier = Modifier.weight(1f),
                            )
                            if (row.availability == Availability.OnDevice) {
                                TextButton(onClick = { model.deleteChapter(row.id) }) { Text("Delete") }
                            }
                            Text(
                                when (row.availability) {
                                    Availability.OnDevice -> "on device"
                                    Availability.OnServer -> "on server"
                                    Availability.NotDownloaded -> "not downloaded"
                                },
                                color = if (row.availability != Availability.NotDownloaded) Tokens.secondary else Tokens.outline,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        HorizontalDivider(color = Tokens.outlineVariant)
                    }
                }
            }
        }
    }
}

internal fun formatNumber(number: Double): String =
    if (number % 1.0 == 0.0) number.toLong().toString() else number.toString()
