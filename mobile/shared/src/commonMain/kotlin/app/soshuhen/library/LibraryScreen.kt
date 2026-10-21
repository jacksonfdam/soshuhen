package app.soshuhen.library

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.api.Series
import app.soshuhen.ui.CoverImage
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.theme.Tokens

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(
    model: LibraryViewModel,
    coverUrl: (Long) -> String,
    onOpen: (Long) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val status by model.status.collectAsStateWithLifecycle()
    val query by model.query.collectAsStateWithLifecycle()

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
        is LoadState.Loaded -> PullToRefreshBox(isRefreshing = false, onRefresh = model::refresh) {
            val all = s.data
            val shown = visible(all, status, query)
            LazyVerticalGrid(
                columns = GridCells.Adaptive(Tokens.coverMinWidth),
                contentPadding = PaddingValues(Tokens.space.lg),
                horizontalArrangement = Arrangement.spacedBy(Tokens.space.md),
                verticalArrangement = Arrangement.spacedBy(Tokens.space.md),
                modifier = Modifier.fillMaxSize(),
            ) {
                s.refreshFailed?.let { message ->
                    item(span = { GridItemSpan(maxLineSpan) }) { Banner(message) }
                }
                item(span = { GridItemSpan(maxLineSpan) }) {
                    OutlinedTextField(
                        value = query,
                        onValueChange = model::setQuery,
                        placeholder = { Text("Search the library") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                val continuing = continueReading(comics(all))
                if (continuing.isNotEmpty() && query.isBlank()) {
                    item(span = { GridItemSpan(maxLineSpan) }) { ContinueRow(continuing, coverUrl, onOpen) }
                }
                item(span = { GridItemSpan(maxLineSpan) }) {
                    StatusChips(comics(all), status, model::setStatus)
                }
                items(shown, key = { it.id }) { CoverCard(it, coverUrl(it.id)) { onOpen(it.id) } }
            }
        }
    }
}

@Composable
private fun Banner(message: String) {
    Text(
        message,
        color = Tokens.onWarning,
        modifier = Modifier.fillMaxWidth()
            .background(Tokens.warning, RoundedCornerShape(Tokens.radius.sm))
            .padding(Tokens.space.md),
    )
}

@Composable
private fun ContinueRow(series: List<Series>, coverUrl: (Long) -> String, onOpen: (Long) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
        Text("Continue reading", style = MaterialTheme.typography.titleMedium)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(Tokens.space.md)) {
            items(series, key = { it.id }) { s ->
                Column(Modifier.width(Tokens.coverMinWidth).clickable { onOpen(s.id) }) {
                    CoverImage(coverUrl(s.id), s.title)
                    Text(s.title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
                    Text("Chapter ${s.progress + 1}", style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant)
                    val total = totalChapters(s)
                    if (total != null) {
                        LinearProgressIndicator(
                            progress = { (s.progress.toFloat() / total).coerceIn(0f, 1f) },
                            color = Tokens.secondary,
                            modifier = Modifier.fillMaxWidth().padding(top = Tokens.space.xs),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusChips(all: List<Series>, status: String?, onChange: (String?) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
        items(STATUS_ORDER) { key ->
            FilterChip(
                selected = status == key,
                onClick = { onChange(key) },
                label = { Text("${STATUS_LABEL.getValue(key)} ${all.count { it.status == key }}") },
            )
        }
        item {
            FilterChip(selected = status == null, onClick = { onChange(null) }, label = { Text("All ${all.size}") })
        }
    }
}

@Composable
private fun CoverCard(series: Series, coverUrl: String, onClick: () -> Unit) {
    Column(Modifier.clickable(onClick = onClick)) {
        Box {
            CoverImage(coverUrl, series.title)
            val count = unread(series)
            if (count > 0) {
                Text(
                    count.toString(),
                    color = Tokens.onPrimaryContainer,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(Tokens.space.xs)
                        .background(Tokens.primaryContainer, RoundedCornerShape(Tokens.radius.sm))
                        .padding(horizontal = Tokens.space.xs),
                )
            }
        }
        Text(series.title, maxLines = 2, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
    }
}
