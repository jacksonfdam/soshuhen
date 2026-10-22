package app.soshuhen.reader

import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.PagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntSize

// Far enough to read small print in a scanned bubble without losing the page.
private const val MAX_ZOOM = 4f

/** Pinch and pan for one page at a time; turning the page puts it back. */
@Stable
internal class Zoom {
    var scale by mutableFloatStateOf(1f)
        private set
    var offset by mutableStateOf(Offset.Zero)
        private set
    private var size = IntSize.Zero

    val zoomed: Boolean get() = scale > 1f

    fun resize(to: IntSize) {
        size = to
    }

    fun change(zoom: Float, pan: Offset) {
        scale = (scale * zoom).coerceIn(1f, MAX_ZOOM)
        // Held inside the page's edges: past them there is only background.
        val maxX = size.width * (scale - 1f) / 2f
        val maxY = size.height * (scale - 1f) / 2f
        val moved = offset + pan
        offset = Offset(moved.x.coerceIn(-maxX, maxX), moved.y.coerceIn(-maxY, maxY))
    }

    fun reset() {
        scale = 1f
        offset = Offset.Zero
    }
}

/**
 * The web's PagedView over a HorizontalPager: one step per spread, then the
 * end of the chapter as a last step of its own, which is where the web's
 * `atEnd` lives.
 */
@Composable
internal fun PagedView(
    pager: PagerState,
    groups: List<List<Int>>,
    source: PageSource,
    mode: String,
    scale: String,
    onTap: (TapAction) -> Unit,
    onEndTap: () -> Unit,
    end: @Composable () -> Unit,
) {
    val zoom = remember(pager) { Zoom() }
    LaunchedEffect(pager.currentPage) { zoom.reset() }
    HorizontalPager(
        state = pager,
        // Manga reads right to left, so the next page comes in from the left.
        reverseLayout = mode == "paged_rtl",
        // A zoomed page pans instead of turning.
        userScrollEnabled = !zoom.zoomed,
        // The web preloads three pages ahead; two either side keeps the
        // decoded pages a phone holds in memory to five spreads.
        beyondViewportPageCount = 2,
        key = { it },
        modifier = Modifier.fillMaxSize(),
    ) { step ->
        if (step >= groups.size) {
            // The web toggles the chrome on any tap here: there is no page to turn.
            Box(Modifier.fillMaxSize().pointerInput(Unit) { detectTapGestures { onEndTap() } }, Alignment.Center) { end() }
            return@HorizontalPager
        }
        val current = step == pager.currentPage
        val state = rememberTransformableState { _, change, pan, _ -> if (current) zoom.change(change, pan) }
        Box(
            Modifier
                .fillMaxSize()
                .clipToBounds()
                .onSizeChanged { if (current) zoom.resize(it) }
                .pointerInput(mode) {
                    detectTapGestures { at -> onTap(tapAction(at.x, size.width.toFloat(), mode)) }
                }
                // Panning only once zoomed, so a plain swipe still reaches the pager.
                .transformable(state, canPan = { zoom.zoomed })
                .graphicsLayer {
                    if (current) {
                        scaleX = zoom.scale
                        scaleY = zoom.scale
                        translationX = zoom.offset.x
                        translationY = zoom.offset.y
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            Spread(groups[step], source, scale)
        }
    }
}

@Composable
private fun Spread(group: List<Int>, source: PageSource, scale: String) {
    if (group.size > 1) {
        // Two halves meeting at the spine, whatever the scale: the web's
        // `max-h-screen w-1/2 object-contain`.
        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.Center) {
            group.forEachIndexed { i, index ->
                PageImage(
                    source, index, ContentScale.Fit,
                    Modifier.weight(1f).fillMaxHeight(),
                    alignment = if (i == 0) Alignment.CenterEnd else Alignment.CenterStart,
                )
            }
        }
        return
    }
    val index = group.first()
    when (scale) {
        // A page taller than the screen scrolls down, as it does on the web.
        "fit_width" -> BoxWithConstraints(Modifier.fillMaxSize()) {
            Box(
                Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().heightIn(min = maxHeight),
                contentAlignment = Alignment.Center,
            ) {
                PageImage(source, index, ContentScale.FillWidth, Modifier.fillMaxWidth())
            }
        }
        // And one wider than the screen scrolls sideways.
        "fit_height" -> BoxWithConstraints(Modifier.fillMaxSize()) {
            Box(
                Modifier.horizontalScroll(rememberScrollState()).fillMaxHeight().widthIn(min = maxWidth),
                contentAlignment = Alignment.Center,
            ) {
                PageImage(source, index, ContentScale.FillHeight, Modifier.fillMaxHeight())
            }
        }
        else -> PageImage(source, index, ContentScale.Fit, Modifier.fillMaxSize())
    }
}
