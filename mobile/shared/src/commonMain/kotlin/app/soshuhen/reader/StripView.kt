package app.soshuhen.reader

import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListLayoutInfo
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import app.soshuhen.ui.theme.Tokens

/**
 * The web's StripView: every page down one column, the end of the chapter
 * after the last. A tap anywhere is for the chrome.
 */
@Composable
internal fun StripView(
    list: LazyListState,
    pageCount: Int,
    source: PageSource,
    scale: String,
    onTap: () -> Unit,
    end: @Composable () -> Unit,
) {
    val zoom = remember(list) { Zoom() }
    // Down a strip the list scrolls up and down by itself, so a zoomed strip
    // pans only sideways; a vertical pan would fight the scroll.
    val state = rememberTransformableState { _, change, pan, _ -> zoom.change(change, Offset(pan.x, 0f)) }
    BoxWithConstraints(
        Modifier
            .fillMaxSize()
            .clipToBounds()
            .onSizeChanged { zoom.resize(it) }
            .pointerInput(Unit) { detectTapGestures { onTap() } }
            .transformable(state, canPan = { zoom.zoomed }),
    ) {
        // A height before the image loads, so the restored position and the
        // visible page have something to measure.
        val placeholder = maxHeight * Tokens.reader.pageMinHeight
        LazyColumn(
            state = list,
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.fillMaxSize().graphicsLayer {
                scaleX = zoom.scale
                scaleY = zoom.scale
                translationX = zoom.offset.x
            },
        ) {
            items(pageCount, key = { it }) { index ->
                Box(Modifier.fillMaxWidth().heightIn(min = placeholder), contentAlignment = Alignment.TopCenter) {
                    PageImage(
                        source, index, ContentScale.FillWidth,
                        // Fit height has no meaning down a strip, so it reads as
                        // a comfortable column the same as fit screen.
                        if (scale == "fit_width") Modifier.fillMaxWidth()
                        else Modifier.widthIn(max = Tokens.reader.columnMaxWidth).fillMaxWidth(),
                    )
                }
            }
            item(key = "end") {
                Box(Modifier.fillMaxWidth().heightIn(min = maxHeight * Tokens.reader.endMinHeight), contentAlignment = Alignment.Center) {
                    end()
                }
            }
        }
    }
}

/**
 * The page with most of itself on screen, as the web's IntersectionObserver
 * picks it; -1 while nothing is laid out.
 */
internal fun mostVisiblePage(info: LazyListLayoutInfo, pageCount: Int): Int {
    var best = -1
    var highest = 0f
    for (item in info.visibleItemsInfo) {
        if (item.index >= pageCount || item.size <= 0) continue
        val top = maxOf(item.offset, info.viewportStartOffset)
        val bottom = minOf(item.offset + item.size, info.viewportEndOffset)
        val ratio = (bottom - top).toFloat() / item.size
        if (ratio > highest) {
            best = item.index
            highest = ratio
        }
    }
    return best
}

/** Whether the end of the chapter has come into view. */
internal fun endVisible(info: LazyListLayoutInfo, pageCount: Int): Boolean =
    info.visibleItemsInfo.any { it.index == pageCount }
