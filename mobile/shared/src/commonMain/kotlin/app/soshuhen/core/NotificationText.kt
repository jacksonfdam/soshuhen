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

/**
 * A series that brought volumes says so in their own count: "3 new chapters"
 * for three light novel volumes would send the reader looking for chapters.
 */
fun newBooksText(title: String, chapters: List<Double>, volumes: List<Double>): Pair<String, String> {
    if (volumes.isEmpty()) return newChaptersText(title, chapters)
    val parts = listOfNotNull(
        chapters.takeIf { it.isNotEmpty() }?.let { newChaptersText(title, it).second },
        counted(volumes, "volume"),
    )
    return title to parts.joinToString(" · ")
}

private fun counted(numbers: List<Double>, noun: String): String {
    val low = formatChapter(numbers.min())
    val high = formatChapter(numbers.max())
    val span = if (low == high) low else "$low–$high"
    return "${numbers.size} new ${if (numbers.size == 1) noun else noun + "s"} ($span)"
}

internal fun formatChapter(number: Double): String =
    if (number % 1.0 == 0.0) number.toLong().toString() else number.toString()
