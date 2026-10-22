package app.soshuhen.ui

import kotlin.math.abs
import kotlin.math.roundToLong
import kotlin.time.Clock
import kotlin.time.Instant

// The same wording as frontend/src/lib/format.ts, so a number or a date reads
// the same on the phone and on the web.

private val units = listOf("second" to 60.0, "minute" to 60.0, "hour" to 24.0, "day" to 7.0, "week" to 4.35, "month" to 12.0)

/** What Intl.RelativeTimeFormat('en', { numeric: 'auto' }) says for [then], as the web's relativeTime. */
fun relativeTime(then: Instant, now: Instant = Clock.System.now()): String {
    var value = (now - then).inWholeMilliseconds / 1000.0
    value = value.roundToLong().toDouble()
    for ((unit, step) in units) {
        if (abs(value) < step) return spoken(-value.roundToLong(), unit)
        value /= step
    }
    return spoken(-value.roundToLong(), "year")
}

private fun spoken(amount: Long, unit: String): String = when {
    amount == 0L && unit == "second" -> "now"
    amount == 0L -> "this $unit"
    unit == "day" && amount == -1L -> "yesterday"
    unit == "day" && amount == 1L -> "tomorrow"
    unit != "second" && unit != "minute" && unit != "hour" && amount == -1L -> "last $unit"
    unit != "second" && unit != "minute" && unit != "hour" && amount == 1L -> "next $unit"
    amount < 0 -> "${-amount} $unit${if (amount == -1L) "" else "s"} ago"
    else -> "in $amount $unit${if (amount == 1L) "" else "s"}"
}

/** MANGA, ONE_SHOT, light_novel as one consistent case, as the web's formatSeriesFormat. */
fun seriesFormat(value: String?): String? = value?.takeIf { it.isNotEmpty() }
    ?.lowercase()?.split('_')?.joinToString(" ") { word -> word.replaceFirstChar { it.uppercase() } }

/** A chapter number without a trailing ".0", as the web's formatChapter. */
fun chapterNumber(number: Double): String =
    if (number % 1.0 == 0.0) number.toLong().toString() else (kotlin.math.round(number * 100) / 100).toString()

private val providerLabel = mapOf("mal" to "MAL", "anilist" to "AniList", "mangadex" to "MangaDex", "comick" to "Comick", "komga" to "Komga")

fun providers(slugs: List<String>): String = slugs.joinToString(" / ") { providerLabel[it] ?: it }

/** A provider's date as toLocaleDateString('en-GB') writes it, or the text as given when it is not a date. */
fun day(iso: String): String {
    val match = Regex("""^(\d{4})-(\d{2})-(\d{2})""").find(iso) ?: return iso
    val (year, month, date) = match.destructured
    return "$date/$month/$year"
}
