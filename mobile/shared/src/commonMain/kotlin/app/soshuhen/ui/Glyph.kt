package app.soshuhen.ui

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

// Navigation glyphs as text: the Material icon artifacts for Compose
// Multiplatform are no longer published alongside 1.12, and two icons do not
// justify drawing vector paths by hand.
@Composable
fun Glyph(symbol: String) = Text(symbol)
