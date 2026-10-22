package app.soshuhen.ui

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Duration.Companion.days
import kotlin.time.Duration.Companion.hours
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant

class FormatTest {
    private val now = Instant.parse("2026-10-22T12:00:00Z")

    // The wording Intl.RelativeTimeFormat('en', { numeric: 'auto' }) gives the web.
    @Test fun relativeTimeSpeaksLikeTheWeb() {
        assertEquals("now", relativeTime(now, now))
        assertEquals("30 seconds ago", relativeTime(now - 30.seconds, now))
        assertEquals("1 minute ago", relativeTime(now - 60.seconds, now))
        assertEquals("1 hour ago", relativeTime(now - 70.minutes, now))
        assertEquals("5 hours ago", relativeTime(now - 5.hours, now))
        assertEquals("yesterday", relativeTime(now - 1.days, now))
        assertEquals("3 days ago", relativeTime(now - 3.days, now))
        assertEquals("last week", relativeTime(now - 8.days, now))
        assertEquals("2 weeks ago", relativeTime(now - 14.days, now))
        assertEquals("last month", relativeTime(now - 40.days, now))
        assertEquals("last year", relativeTime(now - 400.days, now))
        assertEquals("in 3 weeks", relativeTime(now + 21.days, now))
    }

    @Test fun formatsAndProvidersAsTheWebSpellsThem() {
        assertEquals("Light Novel", seriesFormat("LIGHT_NOVEL"))
        assertEquals(null, seriesFormat(null))
        assertEquals("16", chapterNumber(16.0))
        assertEquals("23.5", chapterNumber(23.5))
        assertEquals("AniList / MAL / mangabaka", providers(listOf("anilist", "mal", "mangabaka")))
        assertEquals("10/10/2026", day("2026-10-10"))
    }
}
