package app.soshuhen.core

import kotlin.test.Test
import kotlin.test.assertEquals

class NotificationTextTest {
    @Test fun oneChapter() = assertEquals("Frieren" to "1 new chapter (141)", newChaptersText("Frieren", listOf(141.0)))

    @Test fun severalChapters() =
        assertEquals("Frieren" to "3 new chapters (139–141)", newChaptersText("Frieren", listOf(141.0, 139.0, 140.0)))

    @Test fun fractionalChapter() = assertEquals("Frieren" to "1 new chapter (23.5)", newChaptersText("Frieren", listOf(23.5)))

    @Test fun volumesAreCountedAsVolumes() {
        assertEquals("Tsuki" to "2 new volumes (1–2)", newBooksText("Tsuki", emptyList(), listOf(1.0, 2.0)))
        assertEquals("Tsuki" to "1 new volume (3)", newBooksText("Tsuki", emptyList(), listOf(3.0)))
    }

    @Test fun chaptersAndVolumesTogetherNameBoth() {
        assertEquals(
            "Tsuki" to "2 new chapters (4–5) · 1 new volume (3)",
            newBooksText("Tsuki", listOf(4.0, 5.0), listOf(3.0)),
        )
    }

    @Test fun chaptersAloneReadAsBefore() {
        assertEquals(newChaptersText("F", listOf(1.0)), newBooksText("F", listOf(1.0), emptyList()))
    }
}
