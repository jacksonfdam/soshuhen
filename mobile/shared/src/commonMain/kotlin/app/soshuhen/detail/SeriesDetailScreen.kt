package app.soshuhen.detail

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
import androidx.compose.material3.Button
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
fun SeriesDetailScreen(model: SeriesDetailViewModel, coverUrl: String) {
    val state by model.state.collectAsStateWithLifecycle()
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
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
                        CoverImage(coverUrl, ui.series.title, Modifier.width(Tokens.coverMinWidth))
                        Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                            Text(ui.series.title, style = MaterialTheme.typography.headlineSmall)
                            Text(
                                "Read up to chapter ${ui.series.progress} · ${ui.series.downloaded} on the server",
                                color = Tokens.onSurfaceVariant,
                            )
                            ui.continueWith?.let { next ->
                                // Shown so the layout is the one reading will use;
                                // the reader itself arrives with offline reading.
                                Button(onClick = {}, enabled = false) { Text("Continue chapter ${formatNumber(next.number)}") }
                                Text("Reading arrives in the next update", style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant)
                            }
                        }
                    }
                }
                items(ui.rows, key = { it.id }) { row ->
                    Column {
                        Row(
                            Modifier.fillMaxWidth().padding(vertical = Tokens.space.sm),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(
                                "Chapter ${formatNumber(row.number)}" + (row.title?.let { " · $it" } ?: "") + if (row.read) "  ✓" else "",
                                color = if (row.read) Tokens.onSurfaceVariant else Tokens.onSurface,
                                modifier = Modifier.weight(1f),
                            )
                            Text(
                                when (row.availability) {
                                    Availability.OnServer -> "on server"
                                    Availability.NotDownloaded -> "not downloaded"
                                },
                                color = if (row.availability == Availability.OnServer) Tokens.secondary else Tokens.outline,
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
