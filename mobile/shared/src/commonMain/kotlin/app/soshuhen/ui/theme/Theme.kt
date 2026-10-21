package app.soshuhen.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

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

@Composable
fun SoshuhenTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = soshuhenColorScheme(), content = content)
}
