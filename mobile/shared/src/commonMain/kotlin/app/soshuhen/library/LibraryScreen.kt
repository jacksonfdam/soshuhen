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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.style.TextOverflow
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.api.Series
import app.soshuhen.ui.CoverImage
import app.soshuhen.ui.LoadState
import app.soshuhen.ui.theme.Tokens

const val NOT_ON_DEVICE = "Not on this device. Mark it at home to read it here."

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
    val marked by model.marked.collectAsStateWithLifecycle()
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
            val shown = visible(all, status, query, marked)
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
                notice?.let { message ->
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
                    item(span = { GridItemSpan(maxLineSpan) }) { ContinueRow(continuing, coverUrl, { reachable(it, atHome, marked) }, open) }
                }
                item(span = { GridItemSpan(maxLineSpan) }) {
                    StatusChips(comics(all), marked, status, model::setStatus)
                }
                items(shown, key = { it.id }) { series ->
                    val reachable = reachable(series, atHome, marked)
                    CoverCard(series, coverUrl(series.id), dimmed = !reachable) { open(series) }
                }
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
private fun ContinueRow(
    series: List<Series>,
    coverUrl: (Long) -> String,
    isReachable: (Series) -> Boolean,
    onOpen: (Series) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
        Text("Continue reading", style = MaterialTheme.typography.titleMedium)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(Tokens.space.md)) {
            items(series, key = { it.id }) { s ->
                Column(
                    Modifier.width(Tokens.coverMinWidth)
                        .alpha(if (isReachable(s)) 1f else Tokens.dimmed)
                        .clickable { onOpen(s) },
                ) {
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
private fun StatusChips(all: List<Series>, marked: Set<Long>, status: String?, onChange: (String?) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
        items(STATUS_ORDER) { key ->
            FilterChip(
                selected = status == key,
                onClick = { onChange(key) },
                label = { Text("${STATUS_LABEL.getValue(key)} ${all.count { it.status == key }}") },
            )
        }
        item {
            FilterChip(
                selected = status == ON_DEVICE,
                onClick = { onChange(ON_DEVICE) },
                label = { Text("On device ${all.count { it.id in marked }}") },
            )
        }
        item {
            FilterChip(selected = status == null, onClick = { onChange(null) }, label = { Text("All ${all.size}") })
        }
    }
}

@Composable
private fun CoverCard(series: Series, coverUrl: String, dimmed: Boolean, onClick: () -> Unit) {
    Column(Modifier.alpha(if (dimmed) Tokens.dimmed else 1f).clickable(onClick = onClick)) {
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
