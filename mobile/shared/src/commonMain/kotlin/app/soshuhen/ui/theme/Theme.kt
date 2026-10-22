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
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import app.soshuhen.resources.Res
import app.soshuhen.resources.jetbrains_mono
import app.soshuhen.resources.plus_jakarta_sans
import org.jetbrains.compose.resources.Font
import org.jetbrains.compose.resources.FontResource

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

// google/fonts ships both families as one variable file each, so every weight
// is the same file pinned to a point on its weight axis.
@Composable
private fun variable(resource: FontResource, weights: List<FontWeight>): FontFamily = FontFamily(
    weights.map { weight ->
        Font(resource, weight, variationSettings = FontVariation.Settings(FontVariation.weight(weight.weight)))
    },
)

// Only the weights frontend/src/styles/index.css loads.
private val sansWeights = listOf(FontWeight.Normal, FontWeight.Medium, FontWeight.SemiBold, FontWeight.Bold, FontWeight.ExtraBold)
private val monoWeights = listOf(FontWeight.Normal, FontWeight.Medium, FontWeight.SemiBold)

/** JetBrains Mono, the web's font-mono, which Material's Typography has no slot for. */
val LocalMonoFamily = staticCompositionLocalOf<FontFamily> { FontFamily.Monospace }

/** This style in the web's monospace face, as `font-mono` does on the web. */
@Composable
@ReadOnlyComposable
fun TextStyle.mono(): TextStyle = copy(fontFamily = LocalMonoFamily.current)

@Composable
fun SoshuhenTheme(content: @Composable () -> Unit) {
    val sans = variable(Res.font.plus_jakarta_sans, sansWeights)
    val mono = variable(Res.font.jetbrains_mono, monoWeights)
    val typography = remember(sans) { soshuhenTypography(sans) }
    CompositionLocalProvider(LocalMonoFamily provides mono) {
        MaterialTheme(colorScheme = soshuhenColorScheme(), typography = typography, content = content)
    }
}
