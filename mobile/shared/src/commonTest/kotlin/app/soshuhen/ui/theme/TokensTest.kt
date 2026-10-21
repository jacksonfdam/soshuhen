package app.soshuhen.ui.theme

import androidx.compose.ui.graphics.Color
import kotlin.test.Test
import kotlin.test.assertEquals

class TokensTest {
    @Test
    fun tokensMatchTheWebPalette() {
        assertEquals(Color(0xFF10141A), Tokens.background)
        assertEquals(Color(0xFFD0BCFF), Tokens.primary)
        assertEquals(Color(0xFFA078FF), Tokens.primaryContainer)
        assertEquals(Color(0xFF4EDEA3), Tokens.secondary)
        assertEquals(Color(0xFF6D3BD7), Tokens.inversePrimary)
    }

    @Test
    fun themeUsesTheTokens() {
        val scheme = soshuhenColorScheme()
        assertEquals(Tokens.background, scheme.background)
        assertEquals(Tokens.primary, scheme.primary)
        assertEquals(Tokens.surfaceContainer, scheme.surfaceContainer)
    }
}
