package app.soshuhen.reader

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PageRulesTest {
    @Test fun macResourceForksAreNotPages() { assertFalse(isPage("__MACOSX/._001.jpg")) }
    @Test fun hiddenFilesAreNotPages() { assertFalse(isPage("ch1/.thumb.jpg")) }
    @Test fun comicInfoIsNotAPage() { assertFalse(isPage("ComicInfo.xml")) }
    @Test fun upperCaseExtensionIsAPage() { assertTrue(isPage("001.JPG")) }
    @Test fun directoriesAreNotPages() { assertFalse(isPage("ch1/")) }

    @Test fun naturalOrder() {
        assertEquals(listOf("Page 2.jpg", "Page 10.jpg"), pageOrder(listOf("Page 10.jpg", "Page 2.jpg")))
    }

    @Test fun nestedFoldersSortByFullName() {
        assertEquals(
            listOf("a/2.jpg", "a/10.jpg", "b/1.jpg"),
            pageOrder(listOf("b/1.jpg", "a/10.jpg", "a/2.jpg")),
        )
    }

    @Test fun caseDoesNotDecideTheOrder() {
        assertEquals(listOf("a.jpg", "B.jpg"), pageOrder(listOf("B.jpg", "a.jpg")))
    }

    @Test fun aLongDigitRunDoesNotOverflow() {
        assertEquals(
            listOf("9.jpg", "99999999999999999999999.jpg"),
            pageOrder(listOf("99999999999999999999999.jpg", "9.jpg")),
        )
    }

    @Test fun spreadsCoverAlone() {
        assertEquals(listOf(listOf(0), listOf(1, 2), listOf(3, 4), listOf(5)), spreads(6, "double"))
    }

    @Test fun spreadsSinglePagesOutsideDouble() {
        assertEquals(listOf(listOf(0), listOf(1)), spreads(2, "paged_rtl"))
    }

    @Test fun spreadsOfNothingIsEmpty() { assertEquals(emptyList(), spreads(0, "double")) }

    @Test fun spreadOfFindsThePage() { assertEquals(2, spreadOf(spreads(6, "double"), 4)) }

    @Test fun spreadOfAMissingPageIsTheFirst() { assertEquals(0, spreadOf(spreads(6, "double"), 99)) }
}
