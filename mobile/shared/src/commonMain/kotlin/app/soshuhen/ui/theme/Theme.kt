package app.soshuhen.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import app.soshuhen.resources.Res
import app.soshuhen.resources.jetbrains_mono_medium
import app.soshuhen.resources.jetbrains_mono_regular
import app.soshuhen.resources.jetbrains_mono_semibold
import app.soshuhen.resources.plus_jakarta_sans_bold
import app.soshuhen.resources.plus_jakarta_sans_extrabold
import app.soshuhen.resources.plus_jakarta_sans_medium
import app.soshuhen.resources.plus_jakarta_sans_regular
import app.soshuhen.resources.plus_jakarta_sans_semibold
import org.jetbrains.compose.resources.Font

// Dark only, like the web interface.
fun soshuhenColorScheme(): ColorScheme = darkColorScheme(
    primary = Tokens.primary,
    onPrimary = Tokens.onPrimary,
    primaryContainer = Tokens.primaryContainer,
    onPrimaryContainer = Tokens.onPrimaryContainer,
    inversePrimary = Tokens.inversePrimary,
    secondary = Tokens.secondary,
    onSecondary = Tokens.onSecondary,
    secondaryContainer = Tokens.secondaryContainer,
    onSecondaryContainer = Tokens.onSecondaryContainer,
    tertiary = Tokens.tertiary,
    onTertiary = Tokens.onTertiary,
    tertiaryContainer = Tokens.tertiaryContainer,
    onTertiaryContainer = Tokens.onTertiaryContainer,
    background = Tokens.background,
    onBackground = Tokens.onBackground,
    surface = Tokens.surface,
    onSurface = Tokens.onSurface,
    surfaceVariant = Tokens.surfaceVariant,
    onSurfaceVariant = Tokens.onSurfaceVariant,
    surfaceBright = Tokens.surfaceBright,
    surfaceDim = Tokens.surface,
    surfaceContainerLowest = Tokens.surfaceContainerLowest,
    surfaceContainerLow = Tokens.surfaceContainerLow,
    surfaceContainer = Tokens.surfaceContainer,
    surfaceContainerHigh = Tokens.surfaceContainerHigh,
    surfaceContainerHighest = Tokens.surfaceContainerHighest,
    inverseSurface = Tokens.inverseSurface,
    inverseOnSurface = Tokens.inverseOnSurface,
    outline = Tokens.outline,
    outlineVariant = Tokens.outlineVariant,
    error = Tokens.error,
    onError = Tokens.onError,
    errorContainer = Tokens.errorContainer,
    onErrorContainer = Tokens.onErrorContainer,
)

// One static file per weight, cut from google/fonts' variable files at the
// weights frontend/src/styles/index.css loads, so no weight depends on the
// platform's variation handling. The collapsed spaces these were first blamed
// for came from hinting; see step() in Tokens.kt.
@Composable
internal fun sansFamily(): FontFamily = FontFamily(
    Font(Res.font.plus_jakarta_sans_regular, FontWeight.Normal),
    Font(Res.font.plus_jakarta_sans_medium, FontWeight.Medium),
    Font(Res.font.plus_jakarta_sans_semibold, FontWeight.SemiBold),
    Font(Res.font.plus_jakarta_sans_bold, FontWeight.Bold),
    Font(Res.font.plus_jakarta_sans_extrabold, FontWeight.ExtraBold),
)

@Composable
private fun monoFamily(): FontFamily = FontFamily(
    Font(Res.font.jetbrains_mono_regular, FontWeight.Normal),
    Font(Res.font.jetbrains_mono_medium, FontWeight.Medium),
    Font(Res.font.jetbrains_mono_semibold, FontWeight.SemiBold),
)

/** JetBrains Mono, the web's font-mono, which Material's Typography has no slot for. */
val LocalMonoFamily = staticCompositionLocalOf<FontFamily> { FontFamily.Monospace }

/** This style in the web's monospace face, as `font-mono` does on the web. */
@Composable
@ReadOnlyComposable
fun TextStyle.mono(): TextStyle = copy(fontFamily = LocalMonoFamily.current)

@Composable
fun SoshuhenTheme(content: @Composable () -> Unit) {
    val sans = sansFamily()
    val mono = monoFamily()
    val typography = remember(sans) { soshuhenTypography(sans) }
    CompositionLocalProvider(LocalMonoFamily provides mono) {
        MaterialTheme(colorScheme = soshuhenColorScheme(), typography = typography, content = content)
    }
}
