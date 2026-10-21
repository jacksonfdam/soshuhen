package app.soshuhen.core

import kotlin.test.Test
import kotlin.test.assertEquals

class NotificationTextTest {
    @Test fun oneChapter() = assertEquals("Frieren" to "1 new chapter (141)", newChaptersText("Frieren", listOf(141.0)))

    @Test fun severalChapters() =
        assertEquals("Frieren" to "3 new chapters (139–141)", newChaptersText("Frieren", listOf(141.0, 139.0, 140.0)))

    @Test fun fractionalChapter() = assertEquals("Frieren" to "1 new chapter (23.5)", newChaptersText("Frieren", listOf(23.5)))
}
