package app.soshuhen.ui.theme

import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import kotlin.test.Test
import kotlin.test.assertEquals

class TypographyTest {
    @Test fun typeScaleMatchesTheWeb() {
        val t = soshuhenTypography()
        assertEquals(48.sp, t.displayLarge.fontSize); assertEquals(56.sp, t.displayLarge.lineHeight); assertEquals(FontWeight.ExtraBold, t.displayLarge.fontWeight)
        assertEquals(13.sp, t.labelMedium.fontSize); assertEquals(FontWeight.Medium, t.labelMedium.fontWeight)
        assertEquals(11.sp, t.labelSmall.fontSize); assertEquals(FontWeight.SemiBold, t.labelSmall.fontWeight)
    }

    @Test fun letterSpacingAndTheMiddleStepsMatchTheWeb() {
        val t = soshuhenTypography()
        assertEquals((-0.03).em, t.displayLarge.letterSpacing)
        assertEquals(22.sp, t.headlineMedium.fontSize); assertEquals(30.sp, t.headlineMedium.lineHeight)
        assertEquals(16.sp, t.titleMedium.fontSize); assertEquals(FontWeight.SemiBold, t.titleMedium.fontWeight)
        assertEquals(14.sp, t.bodyMedium.fontSize); assertEquals(22.sp, t.bodyMedium.lineHeight)
        assertEquals(0.04.em, t.labelSmall.letterSpacing)
    }
}
