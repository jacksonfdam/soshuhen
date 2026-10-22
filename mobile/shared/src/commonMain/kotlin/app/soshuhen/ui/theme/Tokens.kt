package app.soshuhen.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * The only place a colour, size, radius or spacing value lives in the app.
 *
 * Copied from frontend/tailwind.config.ts under the same names, so the phone
 * and the web read as one product. Change a value there and here together.
 */
object Tokens {
    val background = Color(0xFF10141A)
    val onBackground = Color(0xFFDFE2EB)
    val surface = Color(0xFF10141A)
    val surfaceBright = Color(0xFF353940)
    val surfaceContainerLowest = Color(0xFF0A0E14)
    val surfaceContainerLow = Color(0xFF181C22)
    val surfaceContainer = Color(0xFF1C2026)
    val surfaceContainerHigh = Color(0xFF262A31)
    val surfaceContainerHighest = Color(0xFF31353C)
    val surfaceVariant = Color(0xFF31353C)
    val onSurface = Color(0xFFDFE2EB)
    val onSurfaceVariant = Color(0xFFCBC3D7)
    val inverseSurface = Color(0xFFDFE2EB)
    val inverseOnSurface = Color(0xFF2D3137)
    val outline = Color(0xFF958EA0)
    val outlineVariant = Color(0xFF494454)
    val primary = Color(0xFFD0BCFF)
    val onPrimary = Color(0xFF3C0091)
    val primaryContainer = Color(0xFFA078FF)
    val onPrimaryContainer = Color(0xFF340080)
    val inversePrimary = Color(0xFF6D3BD7)
    val secondary = Color(0xFF4EDEA3)
    val onSecondary = Color(0xFF003824)
    val secondaryContainer = Color(0xFF00A572)
    val onSecondaryContainer = Color(0xFF00311F)
    val tertiary = Color(0xFF7BD0FF)
    val onTertiary = Color(0xFF00354A)
    val tertiaryContainer = Color(0xFF009BD1)
    val onTertiaryContainer = Color(0xFF002D40)
    val error = Color(0xFFFFB4AB)
    val onError = Color(0xFF690005)
    val errorContainer = Color(0xFF93000A)
    val onErrorContainer = Color(0xFFFFDAD6)
    val warning = Color(0xFFFFB877)
    val onWarning = Color(0xFF4A2600)

    // A page is a scanned image: pure black or white around it is what reading
    // apps use, so the page edge does not read as a frame.
    val readerBlack = Color(0xFF000000)
    val readerGray = Color(0xFF2B2B2B)
    val readerWhite = Color(0xFFFFFFFF)

    object space {
        val xs = 4.dp
        val sm = 8.dp
        val md = 12.dp
        val lg = 16.dp
        val xl = 24.dp
    }

    object radius {
        val sm = 6.dp
        val md = 12.dp
        val lg = 16.dp
        val xl = 24.dp
        val full = 999.dp
    }

    // A series that cannot be opened from here: drawn, but visibly out of reach.
    const val dimmed = 0.4f
    const val coverAspect = 2f / 3f
    val coverMinWidth = 112.dp
    // The cover beside a row in a list, as the web's notification panel draws it.
    val thumbWidth = 36.dp
    // Forms and lists stop growing here on a tablet, so a line stays readable.
    val contentMaxWidth = 560.dp

    // The reader, from frontend/src/features/reader/.
    object reader {
        // TabletChrome's round chapter buttons (h-11 w-11).
        val control = 44.dp
        // PageSlider's page numbers (w-8).
        val pageNumberWidth = 32.dp
        // A strip page's column outside fit width (max-w-3xl).
        val columnMaxWidth = 768.dp
        // A page that failed to load (max-w-xl).
        val placeholderMaxWidth = 576.dp
        // ReaderMessage's detail line (max-w-md).
        val messageMaxWidth = 448.dp
        // The settings sheet's selected tab (border-b-2) and an option's outline (border).
        val tabIndicator = 2.dp
        val hairline = 1.dp
        // The chrome's bars over the page (bg-surface-container/95).
        const val barAlpha = 0.95f
        // Behind a sheet (bg-surface-container-lowest/70).
        const val scrimAlpha = 0.7f
        // A selected option or chapter (bg-primary/[0.12]).
        const val selectedAlpha = 0.12f
        // A sheet's tallest (max-h-[85vh]).
        const val sheetMaxHeight = 0.85f
        // How far a key scrolls a strip (innerHeight * 0.9), leaving a line of overlap.
        const val stripStep = 0.9f
        // EndOfChapter's min-h-[60vh] and a strip page's min-h-[50vh] before it loads.
        const val endMinHeight = 0.6f
        const val pageMinHeight = 0.5f
    }
}
