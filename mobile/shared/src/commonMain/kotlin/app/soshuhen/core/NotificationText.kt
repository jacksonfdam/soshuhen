package app.soshuhen.core

/**
 * The same wording as the web's notification panel, so a chapter reads the
 * same on the phone's shade and in the browser's bell.
 */
fun newChaptersText(title: String, numbers: List<Double>): Pair<String, String> {
    val low = formatChapter(numbers.min())
    val high = formatChapter(numbers.max())
    val span = if (low == high) low else "$low–$high"
    val noun = if (numbers.size == 1) "chapter" else "chapters"
    return title to "${numbers.size} new $noun ($span)"
}

internal fun formatChapter(number: Double): String =
    if (number % 1.0 == 0.0) number.toLong().toString() else number.toString()
