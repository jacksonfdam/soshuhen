package app.soshuhen.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import app.soshuhen.ui.theme.Tokens
import coil3.compose.AsyncImage

/**
 * A cover from the server's own cover route. A series with no cover, or one
 * the server could not fetch, shows its initials instead of an empty box.
 */
@Composable
fun CoverImage(url: String, title: String, modifier: Modifier = Modifier) {
    var failed by remember(url) { mutableStateOf(false) }
    Box(
        modifier
            .aspectRatio(Tokens.coverAspect)
            .clip(RoundedCornerShape(Tokens.radius.sm))
            .background(Tokens.surfaceContainerHigh),
        contentAlignment = Alignment.Center,
    ) {
        if (failed) {
            Text(initials(title), style = MaterialTheme.typography.titleLarge, color = Tokens.onSurfaceVariant)
        } else {
            AsyncImage(
                model = url,
                contentDescription = title,
                contentScale = ContentScale.Crop,
                onError = { failed = true },
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

internal fun initials(title: String): String =
    title.split(' ').filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }
