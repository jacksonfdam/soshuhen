package app.soshuhen.updates

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.core.LocalStore
import app.soshuhen.core.newChaptersText
import app.soshuhen.ui.CoverImage
import app.soshuhen.ui.ProblemBanner
import app.soshuhen.ui.theme.Tokens

/** What the background copy brought in, newest first, a heading per day. */
@Composable
fun UpdatesScreen(
    model: UpdatesViewModel,
    store: LocalStore,
    coverUrl: (Long) -> String,
    onOpen: (Long) -> Unit,
) {
    val rows by model.rows.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize().padding(horizontal = Tokens.space.lg), verticalArrangement = Arrangement.spacedBy(Tokens.space.md)) {
        Text("Updates", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.padding(top = Tokens.space.xl))
        ProblemBanner(store)
        if (rows.isEmpty()) {
            Column(Modifier.fillMaxWidth().padding(Tokens.space.xl), verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                Text("No updates yet", style = MaterialTheme.typography.titleMedium)
                Text("New chapters copied to this device show up here.", color = Tokens.onSurfaceVariant)
            }
        } else {
            LazyColumn(contentPadding = PaddingValues(bottom = Tokens.space.lg)) {
                rows.groupBy { it.day }.forEach { (day, group) ->
                    item(key = "day-$day") {
                        Text(
                            day,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(top = Tokens.space.lg, bottom = Tokens.space.sm),
                        )
                    }
                    items(group, key = { it.chapterId }) { row -> UpdateRow(row, coverUrl(row.seriesId), onOpen) }
                }
            }
        }
    }
}

@Composable
private fun UpdateRow(row: ImportLogRow, coverUrl: String, onOpen: (Long) -> Unit) {
    val (title, text) = newChaptersText(row.seriesTitle, listOf(row.number))
    Row(
        Modifier.fillMaxWidth().clickable { onOpen(row.seriesId) }.padding(vertical = Tokens.space.sm),
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CoverImage(coverUrl, row.seriesTitle, Modifier.width(Tokens.thumbWidth))
        Column(Modifier.weight(1f)) {
            Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
            Text(text, color = Tokens.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        }
    }
}
