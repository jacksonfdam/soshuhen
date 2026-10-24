package app.soshuhen.reader

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.animateScrollBy
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.pager.rememberPagerState
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.ui.theme.Tokens
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch

/** The web's ReaderPage, full screen over the shell. */
@Composable
fun ReaderScreen(model: ReaderViewModel, seriesTitle: String, onBack: () -> Unit) {
    val state by model.state.collectAsStateWithLifecycle()
    when (val s = state) {
        ReaderState.Loading -> ReaderMessage("Opening…", null, onBack)
        is ReaderState.Unavailable -> ReaderMessage("This chapter cannot be read", s.message, onBack)
        is ReaderState.Ready -> Reader(s.ui, seriesTitle, model, onBack)
    }
}

@Composable
private fun Reader(ui: ReaderUi, seriesTitle: String, model: ReaderViewModel, onBack: () -> Unit) {
    val mode = ui.prefs.mode
    var panel by remember { mutableStateOf<Panel?>(null) }
    val background = when (ui.prefs.background) {
        "white" -> Tokens.readerWhite
        "gray" -> Tokens.readerGray
        else -> Tokens.readerBlack
    }
    // A fresh view per chapter and per mode, as the web keys its reader by
    // chapter: kept across, the pager or the strip of the last one would
    // scroll the new one to its old place and save that as a position.
    key(ui.chapter.id, mode) {
        val scope = rememberCoroutineScope()
        val current by rememberUpdatedState(ui)
        val strip = mode == "long_strip"
        val groups = remember(ui.pageCount, mode) { spreads(ui.pageCount, mode) }
        // Both are cheap to hold; only the one for this mode is ever drawn.
        val list = rememberLazyListState(initialFirstVisibleItemIndex = ui.page)
        val pager = rememberPagerState(initialPage = spreadOf(groups, ui.page)) { groups.size + 1 }
        val scrollStrip = { sign: Float ->
            scope.launch { list.animateScrollBy(sign * list.layoutInfo.viewportSize.height * Tokens.reader.stripStep) }
        }
        val forward: () -> Unit = {
            if (strip) {
                scrollStrip(1f)
            } else {
                scope.launch {
                    if (pager.currentPage < groups.size) pager.animateScrollToPage(pager.currentPage + 1)
                    else current.next?.let(model::openChapter)
                }
            }
        }
        val back: () -> Unit = {
            if (strip) {
                scrollStrip(-1f)
            } else {
                scope.launch {
                    if (pager.currentPage > 0) pager.animateScrollToPage(pager.currentPage - 1)
                    else current.previous?.let(model::openChapter)
                }
            }
        }
        // Down a strip a page is a place in the scroll, not a state to set.
        val seek: (Int) -> Unit = { index ->
            if (strip) {
                scope.launch { list.scrollToItem(index) }
            } else {
                model.goTo(index)
                scope.launch { pager.scrollToPage(spreadOf(groups, index)) }
            }
        }
        val end: @Composable () -> Unit = {
            EndOfChapter(ui, onNext = { ui.next?.let(model::openChapter) }, onBack = onBack)
        }
        if (strip) {
            LaunchedEffect(list) {
                snapshotFlow { mostVisiblePage(list.layoutInfo, current.pageCount) }
                    .distinctUntilChanged()
                    // The opening page is already the position; saving it
                    // again on open would only repeat it to the server.
                    .filter { it >= 0 && it != current.page }
                    .collect { model.goTo(it) }
            }
            LaunchedEffect(list) {
                // The web's onEnd: reaching the end of the strip finishes the chapter.
                snapshotFlow { endVisible(list.layoutInfo, current.pageCount) }
                    .distinctUntilChanged()
                    .filter { it }
                    .collect { model.goTo(current.pageCount - 1) }
            }
        } else {
            LaunchedEffect(pager) {
                snapshotFlow { pager.settledPage }.collect { step ->
                    if (step < groups.size) {
                        if (current.page !in groups[step]) model.goTo(groups[step].first())
                    } else {
                        // Past the last spread: the VM's forward step there is what
                        // finishes the chapter, even one that opened on its last page.
                        model.nextPage()
                    }
                }
            }
        }
        // Collected only while a chapter is on screen, so the volume buttons
        // change the volume again everywhere else, the loading screen included.
        LaunchedEffect(Unit) {
            ReaderKeys.events.collect {
                when (it) {
                    ReaderKey.Next -> forward()
                    ReaderKey.Previous -> back()
                }
            }
        }
        Box(Modifier.fillMaxSize().background(background)) {
            if (strip) {
                StripView(list, ui.pageCount, ui.source, ui.prefs.scale, onTap = model::toggleChrome, end = end)
            } else {
                PagedView(
                    pager, groups, ui.source, mode, ui.prefs.scale,
                    onTap = { action ->
                        when (action) {
                            TapAction.Next -> forward()
                            TapAction.Previous -> back()
                            TapAction.Chrome -> model.toggleChrome()
                        }
                    },
                    onEndTap = model::toggleChrome,
                    end = end,
                )
            }
            if (ui.chromeVisible) {
                ReaderChrome(
                    ui, seriesTitle, rtl = mode == "paged_rtl", onBack = onBack, onSeek = seek,
                    onOpenChapter = model::openChapter, onPanel = { panel = it },
                )
            }
        }
    }
    when (panel) {
        Panel.Settings -> SettingsSheet(ui.prefs, onChange = model::setPrefs, onClose = { panel = null })
        Panel.Chapters -> ChapterSheet(ui, onOpen = { id -> panel = null; model.openChapter(id) }, onClose = { panel = null })
        null -> Unit
    }
}

/** The web's EndOfChapter: where the next chapter is one tap away. */
@Composable
private fun EndOfChapter(ui: ReaderUi, onNext: () -> Unit, onBack: () -> Unit) {
    val next = ui.chapters.firstOrNull { it.id == ui.next }
    Column(
        Modifier.fillMaxWidth().padding(horizontal = Tokens.space.lg),
        verticalArrangement = Arrangement.spacedBy(Tokens.space.md, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "End of Ch. ${formatChapter(ui.chapter.number)}",
            style = MaterialTheme.typography.labelMedium, fontFamily = FontFamily.Monospace,
            color = Tokens.onSurfaceVariant, textAlign = TextAlign.Center,
        )
        if (ui.next != null) {
            val label = next?.let { "Ch. ${formatChapter(it.number)}" + (it.title?.let { t -> " · $t" } ?: "") } ?: "Next chapter"
            ReaderButton(label, onNext, primary = true, glyph = "›")
        } else {
            Text("You are caught up.", style = MaterialTheme.typography.bodyMedium, color = Tokens.onSurface)
            ReaderButton("Back to the series", onBack)
        }
    }
}

/** The web's ReaderMessage: every state the reader shows before it has a page. */
@Composable
internal fun ReaderMessage(title: String, detail: String?, onBack: () -> Unit) {
    Column(
        Modifier.fillMaxSize().background(Tokens.readerBlack).padding(horizontal = Tokens.space.lg),
        verticalArrangement = Arrangement.spacedBy(Tokens.space.md, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(title, style = MaterialTheme.typography.titleLarge, color = Tokens.onSurface, textAlign = TextAlign.Center)
        detail?.let {
            Text(
                it, Modifier.widthIn(max = Tokens.reader.messageMaxWidth),
                style = MaterialTheme.typography.bodyMedium, color = Tokens.onSurfaceVariant, textAlign = TextAlign.Center,
            )
        }
        ReaderButton("Back", onBack)
    }
}
