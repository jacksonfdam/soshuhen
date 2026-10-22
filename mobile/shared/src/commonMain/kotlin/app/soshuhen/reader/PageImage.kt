package app.soshuhen.reader

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import app.soshuhen.ui.theme.Tokens
import coil3.compose.AsyncImage
import coil3.compose.LocalPlatformContext
import coil3.request.CachePolicy
import coil3.request.ImageRequest

/**
 * One page, or a page-sized placeholder that says it could not load, as the
 * web's PageImage: one failed page must not take the chapter down with it.
 */
@Composable
internal fun PageImage(
    source: PageSource,
    index: Int,
    contentScale: ContentScale,
    modifier: Modifier = Modifier,
    alignment: Alignment = Alignment.Center,
) {
    var attempt by remember(source, index) { mutableIntStateOf(0) }
    var failed by remember(source, index) { mutableStateOf(false) }
    if (failed) {
        Column(
            modifier.widthIn(max = Tokens.reader.placeholderMaxWidth).fillMaxWidth()
                .aspectRatio(Tokens.coverAspect).background(Tokens.surfaceContainer),
            verticalArrangement = Arrangement.spacedBy(Tokens.space.md, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Page ${index + 1} could not be loaded.", style = MaterialTheme.typography.bodyMedium, color = Tokens.onSurfaceVariant)
            ReaderButton("Try again", onClick = {
                failed = false
                attempt++
            })
        }
        return
    }
    val context = LocalPlatformContext.current
    // A new request per attempt is what makes a retry ask again; Coil keeps no
    // memory of a failure, only of what loaded.
    val request = remember(source, index, attempt) {
        ImageRequest.Builder(context)
            .data(
                when (source) {
                    is PageSource.Device -> source.pages[index]
                    is PageSource.Server -> source.api.pageUrl(source.chapterId, index)
                },
            )
            // The disk cache keeps covers for reading away from home; a
            // chapter's pages would push them out within a few hundred pages.
            .diskCachePolicy(CachePolicy.DISABLED)
            .build()
    }
    AsyncImage(
        model = request,
        contentDescription = "Page ${index + 1}",
        contentScale = contentScale,
        alignment = alignment,
        onError = { failed = true },
        modifier = modifier,
    )
}
