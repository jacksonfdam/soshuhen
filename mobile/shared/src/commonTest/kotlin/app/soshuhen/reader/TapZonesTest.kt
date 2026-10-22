package app.soshuhen.reader

import kotlin.test.Test
import kotlin.test.assertEquals

class TapZonesTest {
    @Test fun rtlLeftIsNext() = assertEquals(TapAction.Next, tapAction(10f, 900f, "paged_rtl"))
    @Test fun ltrLeftIsPrevious() = assertEquals(TapAction.Previous, tapAction(10f, 900f, "paged_ltr"))
    @Test fun middleToggles() = assertEquals(TapAction.Chrome, tapAction(450f, 900f, "paged_rtl"))
    @Test fun stripAlwaysToggles() = assertEquals(TapAction.Chrome, tapAction(10f, 900f, "long_strip"))

    @Test fun rtlRightIsPrevious() = assertEquals(TapAction.Previous, tapAction(890f, 900f, "paged_rtl"))
    @Test fun ltrRightIsNext() = assertEquals(TapAction.Next, tapAction(890f, 900f, "paged_ltr"))
    @Test fun doubleLeftIsPrevious() = assertEquals(TapAction.Previous, tapAction(10f, 900f, "double"))
    @Test fun doubleRightIsNext() = assertEquals(TapAction.Next, tapAction(890f, 900f, "double"))

    // The web splits at exactly a third: x < 1/3 is left, x > 2/3 is right.
    @Test fun thirdsAreTheMiddle() {
        assertEquals(TapAction.Chrome, tapAction(300f, 900f, "paged_ltr"))
        assertEquals(TapAction.Chrome, tapAction(600f, 900f, "paged_ltr"))
        assertEquals(TapAction.Previous, tapAction(299f, 900f, "paged_ltr"))
        assertEquals(TapAction.Next, tapAction(601f, 900f, "paged_ltr"))
    }

    @Test fun zeroWidthToggles() = assertEquals(TapAction.Chrome, tapAction(0f, 0f, "paged_ltr"))
}
