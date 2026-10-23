package app.soshuhen.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextMotion
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

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
    val warningContainer = Color(0xFFC2691A)
    val onWarningContainer = Color(0xFF3A1D00)
    // The cover's hairline (border-white/[0.08]) and the panel dividers (border-white/5).
    val coverEdge = Color(0x14FFFFFF)
    val divider = Color(0x0DFFFFFF)

    // A page is a scanned image: pure black or white around it is what reading
    // apps use, so the page edge does not read as a frame.
    val readerBlack = Color(0xFF000000)
    val readerGray = Color(0xFF2B2B2B)
    val readerWhite = Color(0xFFFFFFFF)

    // Tailwind's numeric steps (1, 2, 3, 4, 6), which is what most web classes
    // use; the web's own named steps are below them under their web names.
    object space {
        val xxs = 2.dp
        val xs = 4.dp
        val xsPlus = 6.dp
        val sm = 8.dp
        val smPlus = 10.dp
        val md = 12.dp
        val mdPlus = 14.dp
        val lg = 16.dp
        val gutter = 20.dp
        val xl = 24.dp
        val margin = 32.dp
        val xxl = 40.dp
    }

    // tailwind.config.ts overrides the scale, so rounded-lg is 16 and rounded-xl
    // 24 there, not Tailwind's defaults; rounded-2xl is Tailwind's own 16.
    object radius {
        val sm = 4.dp
        val base = 8.dp
        val md = 12.dp
        val lg = 16.dp
        val xl = 24.dp
        val full = 999.dp
    }

    // Icon sizes the web draws at (h-3, h-3.5, h-4, h-5, h-6).
    object icon {
        val xs = 12.dp
        val sm = 14.dp
        val md = 16.dp
        val lg = 20.dp
        val xl = 24.dp
    }

    // Fixed boxes from frontend/src/features/ and frontend/src/ui/.
    object box {
        // The cover's progress strip (h-1) and every ProgressBar.
        val bar = 4.dp
        // A status pill's dot (h-1.5) and an unread dot (h-2).
        val dot = 6.dp
        val dotLg = 8.dp
        // SettingsPage's section tile (h-7) and ProviderCard's tile (h-12).
        val sectionTile = 28.dp
        val providerTile = 48.dp
        // EmptyState's icon disc (h-12).
        val emptyIcon = 48.dp
        // ContinueReading's cover (h-28 w-20).
        val continueCoverWidth = 80.dp
        val continueCoverHeight = 112.dp
        // The notification panel's cover (h-12 w-9).
        val thumbHeight = 48.dp
        // SeriesDetailPage's cover (w-56, sm:w-64).
        val heroCover = 224.dp
        val heroCoverWide = 256.dp
        // SeriesGrid: two columns on a phone, then auto-fill minmax(160px, 220px) from sm.
        // CSS sizes those tracks by the 220, so the 160 never enters the arithmetic.
        val gridMax = 220.dp
        val sm = 640.dp
        val md = 768.dp
        val lg = 1024.dp
        // Where AppShell swaps its bottom bar for the header nav (xl:hidden).
        val xl = 1280.dp
        // Toggle's track (h-6 w-11) and thumb (h-4).
        val toggleWidth = 44.dp
        val toggleHeight = 24.dp
        val toggleThumb = 16.dp
        // EmptyState's detail line (max-w-sm).
        val emptyDetailMax = 384.dp
        // ChapterTable shows this many rows before "Show all".
        const val previewRows = 20
    }

    // shadow-card (0 8px 24px -4px) and shadow-xs, as Material elevations.
    val cardElevation = 8.dp
    val smallElevation = 1.dp
    val hairline = 1.dp

    // Alphas the web writes as a slash: /85 behind a badge on a cover, /80 on the
    // needs-review badge, /20 behind an error notice, /[0.12] behind a pill.
    const val overlayAlpha = 0.85f
    const val reviewAlpha = 0.8f
    // A needs-review cover's edge (border-error/40) and the card's rule (border-surface-container-highest/40).
    const val reviewBorderAlpha = 0.4f
    const val ruleAlpha = 0.4f
    // A chapter row's own rule (border-surface-container-highest/20).
    const val rowRuleAlpha = 0.2f
    const val noticeAlpha = 0.2f
    const val tintAlpha = 0.12f
    // A disabled control (disabled:opacity-50).
    const val disabledAlpha = 0.5f
    const val unreadAlpha = 0.1f
    const val countAlpha = 0.2f
    const val readTitleAlpha = 0.7f
    const val filterPanelAlpha = 0.6f

    // A series that cannot be opened from here: drawn, but visibly out of reach.
    const val dimmed = 0.4f
    const val coverAspect = 2f / 3f
    val coverMinWidth = 112.dp
    // The cover beside a row in a list, as the web's notification panel draws it.
    val thumbWidth = 36.dp
    // Onboarding's forms, which have no web page to follow, stop growing here.
    val contentMaxWidth = 560.dp
    // AppShell's max-w-canvas: every web page fills the window up to this and
    // is centred beyond it.
    val canvasMaxWidth = 1440.dp

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

// The web's type scale from frontend/tailwind.config.ts, size / line height /
// tracking / weight as written there. Material's roles map onto it by size;
// where Material has a step the web does not, the nearest web step stands in
// rather than an invented one.
//
// Every step is laid out unhinted, at subpixel positions. Compose's default
// (TextMotion.Static) hints glyphs to whole pixels, and a Galaxy Tab A on
// Android 11 at font scale 1.1 autohints Plus Jakarta Sans, which ships no
// hints of its own, until a 12sp space is a pixel wide: "Plantoread". The stock
// emulator rasterises the same text with its spaces intact.
private fun step(size: Int, line: Int, weight: FontWeight, tracking: TextUnit, family: FontFamily) = TextStyle(
    fontFamily = family,
    fontSize = size.sp,
    lineHeight = line.sp,
    fontWeight = weight,
    letterSpacing = tracking,
    textMotion = TextMotion.Animated,
)

fun soshuhenTypography(sans: FontFamily = FontFamily.Default): Typography {
    val displayLg = step(48, 56, FontWeight.ExtraBold, (-0.03).em, sans)
    val displaySm = step(36, 44, FontWeight.Bold, (-0.02).em, sans)
    val headlineLg = step(28, 36, FontWeight.Bold, (-0.02).em, sans)
    val headlineMd = step(22, 30, FontWeight.SemiBold, (-0.01).em, sans)
    val headlineSm = step(18, 24, FontWeight.SemiBold, 0.em, sans)
    val titleMd = step(16, 22, FontWeight.SemiBold, 0.em, sans)
    val bodyLg = step(16, 26, FontWeight.Normal, 0.em, sans)
    val bodyMd = step(14, 22, FontWeight.Normal, 0.em, sans)
    val bodySm = step(12, 18, FontWeight.Normal, 0.em, sans)
    val labelMd = step(13, 18, FontWeight.Medium, 0.02.em, sans)
    val labelSm = step(11, 15, FontWeight.SemiBold, 0.04.em, sans)
    return Typography(
        displayLarge = displayLg,
        displayMedium = displaySm,
        displaySmall = displaySm,
        headlineLarge = headlineLg,
        headlineMedium = headlineMd,
        headlineSmall = headlineSm,
        titleLarge = headlineSm,
        titleMedium = titleMd,
        // The Chip's text-body-sm font-semibold.
        titleSmall = bodySm.copy(fontWeight = FontWeight.SemiBold),
        bodyLarge = bodyLg,
        bodyMedium = bodyMd,
        bodySmall = bodySm,
        // Every web Button is text-label-md.
        labelLarge = labelMd,
        labelMedium = labelMd,
        labelSmall = labelSm,
    )
}
