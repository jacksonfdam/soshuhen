package app.soshuhen.reader

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.animateScrollBy
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.core.BookKind
import app.soshuhen.ui.theme.Tokens
import app.soshuhen.ui.theme.sansFamily
import coil3.compose.AsyncImage
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch

@Composable
fun ProseReaderScreen(model: ProseReaderViewModel, seriesTitle: String, onBack: () -> Unit) {
    val state by model.state.collectAsStateWithLifecycle()
    when (val s = state) {
        ProseState.Loading -> ReaderMessage("Opening…", null, onBack)
        is ProseState.Unavailable -> ReaderMessage("This book cannot be read", s.message, onBack)
        is ProseState.Ready -> ProseReader(s.ui, seriesTitle, model, onBack)
    }
}

private class Ink(val background: Color, val text: Color)

private fun ink(background: String) = when (background) {
    "white" -> Ink(Tokens.readerWhite, Tokens.proseInkDark)
    "sepia" -> Ink(Tokens.readerSepia, Tokens.proseInkSepia)
    "gray" -> Ink(Tokens.readerGray, Tokens.onSurface)
    else -> Ink(Tokens.readerBlack, Tokens.onSurface)
}

@Composable
private fun family(font: String): FontFamily = when (font) {
    "sans" -> FontFamily.SansSerif
    "app" -> sansFamily()
    else -> FontFamily.Serif
}

private class Styles(val body: TextStyle, val heading: TextStyle)

@Composable
private fun styles(style: ProseStyle, color: Color): Styles {
    val family = family(style.font)
    val body = TextStyle(
        fontFamily = family,
        fontSize = style.fontSize.sp,
        lineHeight = (style.fontSize * Tokens.prose.lineHeight).sp,
        color = color,
    )
    val headingSize = style.fontSize * Tokens.prose.headingScale
    return Styles(body, body.copy(fontSize = headingSize.sp, lineHeight = (headingSize * Tokens.prose.lineHeight).sp, fontWeight = FontWeight.Bold))
}

@Composable
private fun ProseReader(ui: ProseUi, seriesTitle: String, model: ProseReaderViewModel, onBack: () -> Unit) {
    var settings by remember { mutableStateOf(false) }
    var ended by remember(ui.ref) { mutableStateOf(false) }
    val ink = ink(ui.style.background)
    val styles = styles(ui.style, ink.text)
    val current by rememberUpdatedState(ui)
    val openNext = { current.next?.let(model::open) ?: Unit }
    val openPrevious = { current.previous?.let(model::open) ?: Unit }
    val itemLabel = if (ui.ref.kind == BookKind.Volume) "volume" else "chapter"

    Box(Modifier.fillMaxSize().background(ink.background)) {
        // A fresh view per book and per direction, as the manga reader keys
        // its own: a strip kept across would scroll the new book to the old place.
        key(ui.ref, ui.mode) {
            if (ended) {
                EndOfBook(ui, ink, itemLabel, onNext = openNext, onBack = onBack, onReturn = { ended = false })
            } else if (ui.mode == "long_strip") {
                ScrollView(ui, styles, ink, model)
            } else {
                PagedProse(
                    ui, styles, ink, model,
                    onEnd = { ended = true },
                    onBeforeStart = openPrevious,
                )
            }
        }
        if (ui.chromeVisible && !ended) {
            ProseChrome(ui, seriesTitle, model, onBack, onSettings = { settings = true })
        }
    }
    if (settings) ProseSettings(ui, model, onClose = { settings = false })
}

/** Where a page turn lands: forward and back, as the mode and the edges say. */
private fun Modifier.turns(mode: String, onForward: () -> Unit, onBack: () -> Unit, onChrome: () -> Unit): Modifier =
    pointerInput(mode) {
        detectTapGestures { offset ->
            when (tapAction(offset.x, size.width.toFloat(), mode)) {
                TapAction.Next -> onForward()
                TapAction.Previous -> onBack()
                TapAction.Chrome -> onChrome()
            }
        }
    }.pointerInput(mode) {
        var dragged = 0f
        detectHorizontalDragGestures(
            onDragStart = { dragged = 0f },
            onDragEnd = {
                if (kotlin.math.abs(dragged) > size.width * Tokens.prose.swipe) {
                    // A swipe pulls the next page in from the side it lies on.
                    val towardStart = dragged > 0
                    val forward = if (mode == "paged_rtl") towardStart else !towardStart
                    if (forward) onForward() else onBack()
                }
            },
        ) { _, amount -> dragged += amount }
    }

@Composable
private fun PagedProse(
    ui: ProseUi,
    styles: Styles,
    ink: Ink,
    model: ProseReaderViewModel,
    onEnd: () -> Unit,
    onBeforeStart: () -> Unit,
) {
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val double = ui.mode == "double"
        val margin = with(density) { Tokens.prose.marginHorizontal.roundToPx() }
        val marginV = with(density) { Tokens.prose.marginVertical.roundToPx() }
        val gutter = if (double) with(density) { Tokens.prose.doubleGutter.roundToPx() } else 0
        val total = constraints.maxWidth - 2 * margin
        val pageWidth = if (double) (total - gutter) / 2 else total
        val pageHeight = constraints.maxHeight - 2 * marginV
        val gap = with(density) { Tokens.prose.paragraphGap.roundToPx() }
        val paginator = remember(ui.book, pageWidth, pageHeight, styles.body, styles.heading) {
            Paginator(ui.book, ComposeMeasure(measurer, styles.body, styles.heading, pageHeight), pageWidth, pageHeight, gap)
        }
        val left = paginator.pageFrom(ui.position)
        val right = if (double && !paginator.isLast(left)) paginator.pageFrom(left.end) else null
        val last = right ?: left
        LaunchedEffect(last) {
            // Reaching the last page is finishing the book, as the manga reader counts it.
            if (paginator.isLast(last)) model.finish()
        }
        val forward = {
            if (paginator.isLast(last)) onEnd() else model.moveTo(last.end)
        }
        val back = {
            val before = paginator.pageBefore(left.start)
            if (before == null) {
                onBeforeStart()
            } else {
                val further = if (double) paginator.pageBefore(before.start) else null
                model.moveTo((further ?: before).start)
            }
        }
        // The gesture and key handlers outlive a composition; through these they
        // always turn from the page on screen now, not the one they started on.
        val forwardNow by rememberUpdatedState(forward)
        val backNow by rememberUpdatedState(back)
        LaunchedEffect(Unit) {
            ReaderKeys.events.collect {
                when (it) {
                    ReaderKey.Next -> forwardNow()
                    ReaderKey.Previous -> backNow()
                }
            }
        }
        Row(
            Modifier.fillMaxSize()
                .turns(ui.mode, onForward = { forwardNow() }, onBack = { backNow() }, onChrome = model::toggleChrome)
                .padding(horizontal = Tokens.prose.marginHorizontal, vertical = Tokens.prose.marginVertical),
            horizontalArrangement = Arrangement.spacedBy(Tokens.prose.doubleGutter),
        ) {
            val pageModifier = with(density) { Modifier.width(pageWidth.toDp()).fillMaxHeight() }
            PageContent(ui.book, left, styles, ink, pageHeight, pageModifier)
            right?.let { PageContent(ui.book, it, styles, ink, pageHeight, pageModifier) }
        }
    }
}

/** The blocks of [page], the first and last cut where the page was cut. */
@Composable
private fun PageContent(book: Book, page: Page, styles: Styles, ink: Ink, pageHeight: Int, modifier: Modifier) {
    val density = LocalDensity.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(Tokens.prose.paragraphGap)) {
        val s = page.start.section
        val section = book.sections[s]
        val lastBlock = if (page.end.section == s) page.end.block else section.lastIndex
        for (b in page.start.block..lastBlock) {
            val block = section[b]
            val from = if (b == page.start.block) page.start.offset else 0
            val to = if (page.end.section == s && b == page.end.block) page.end.offset else block.length()
            if (to <= from) continue
            when (block) {
                is Block.Paragraph -> Text(block.text.annotated(from, minOf(to, block.text.text.length)), style = styles.body)
                is Block.Heading -> Text(block.text.annotated(from, minOf(to, block.text.text.length)), style = styles.heading)
                is Block.Image -> AsyncImage(
                    model = block.path,
                    contentDescription = null,
                    contentScale = ContentScale.Fit,
                    modifier = with(density) { Modifier.fillMaxWidth().height(pageHeight.toDp()) },
                )
                Block.Break -> Text(SCENE_BREAK, Modifier.fillMaxWidth(), style = styles.body, textAlign = TextAlign.Center)
            }
        }
    }
}

/** Every block of every section in one list, for the scrolling mode. */
private fun flatten(book: Book): List<Pair<Int, Int>> =
    book.sections.flatMapIndexed { s, section -> section.indices.map { s to it } }

@Composable
private fun ScrollView(ui: ProseUi, styles: Styles, ink: Ink, model: ProseReaderViewModel) {
    val items = remember(ui.book) { flatten(ui.book) }
    val startIndex = remember(ui.book) { items.indexOf(ui.position.section to ui.position.block).coerceAtLeast(0) }
    val list = rememberLazyListState(initialFirstVisibleItemIndex = startIndex)
    val scope = rememberCoroutineScope()
    val current by rememberUpdatedState(ui)
    // The place the scroll itself last reported. Any other place came from the
    // slider, and the list has to be taken there.
    var reported by remember(ui.book) { mutableStateOf(ui.position) }
    LaunchedEffect(list) {
        snapshotFlow { scrolledTo(list, items, current.book) }
            .distinctUntilChanged()
            .filter { it != null }
            .collect {
                reported = it!!
                model.moveTo(it)
            }
    }
    LaunchedEffect(ui.position) {
        if (ui.position != reported) {
            reported = ui.position
            list.scrollToItem(items.indexOf(ui.position.section to ui.position.block).coerceAtLeast(0))
        }
    }
    LaunchedEffect(list) {
        // The end of the last block on screen is the end of the book.
        snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.let { it.index == items.lastIndex && it.offset + it.size <= list.layoutInfo.viewportEndOffset } == true }
            .distinctUntilChanged()
            .filter { it }
            .collect { model.finish() }
    }
    LaunchedEffect(Unit) {
        ReaderKeys.events.collect {
            val step = list.layoutInfo.viewportSize.height * Tokens.reader.stripStep
            scope.launch { list.animateScrollBy(if (it == ReaderKey.Next) step else -step) }
        }
    }
    LazyColumn(
        Modifier.fillMaxSize().pointerInput(Unit) { detectTapGestures { model.toggleChrome() } },
        state = list,
        contentPadding = androidx.compose.foundation.layout.PaddingValues(
            horizontal = Tokens.prose.marginHorizontal, vertical = Tokens.prose.marginVertical,
        ),
        verticalArrangement = Arrangement.spacedBy(Tokens.prose.paragraphGap),
    ) {
        itemsIndexed(items) { _, (s, b) ->
            when (val block = ui.book.sections[s][b]) {
                is Block.Paragraph -> Text(block.text.annotated(), style = styles.body)
                is Block.Heading -> Text(block.text.annotated(), style = styles.heading)
                is Block.Image -> AsyncImage(block.path, null, Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth)
                Block.Break -> Text(SCENE_BREAK, Modifier.fillMaxWidth(), style = styles.body, textAlign = TextAlign.Center)
            }
        }
    }
}

/** The first visible block, and how far into it the top of the screen is, as a character. */
private fun scrolledTo(list: LazyListState, items: List<Pair<Int, Int>>, book: Book): ProsePosition? {
    val first = list.layoutInfo.visibleItemsInfo.firstOrNull() ?: return null
    val (s, b) = items.getOrNull(first.index) ?: return null
    val block = book.sections[s][b]
    val into = if (first.size > 0) (-first.offset).coerceAtLeast(0).toFloat() / first.size else 0f
    return ProsePosition(s, b, (into * block.length()).toInt().coerceIn(0, block.length() - 1))
}

@Composable
private fun EndOfBook(ui: ProseUi, ink: Ink, itemLabel: String, onNext: () -> Unit, onBack: () -> Unit, onReturn: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = Tokens.space.lg)
            .pointerInput(Unit) { detectTapGestures { onReturn() } },
        verticalArrangement = Arrangement.spacedBy(Tokens.space.md, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "End of ${ui.title}", style = MaterialTheme.typography.labelMedium, fontFamily = FontFamily.Monospace,
            color = ink.text, textAlign = TextAlign.Center,
        )
        if (ui.next != null) {
            ReaderButton("Next $itemLabel", onNext, primary = true, glyph = "›")
        } else {
            Text("You are caught up.", style = MaterialTheme.typography.bodyMedium, color = ink.text)
        }
        ReaderButton("Back to the series", onBack)
    }
}
