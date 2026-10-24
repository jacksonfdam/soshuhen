package app.soshuhen.reader

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Constraints
import kotlin.math.ceil

/** What a scene break is drawn as, measured and shown the same way. */
internal const val SCENE_BREAK = "*   *   *"

/** [from] and [to] cut the text, keeping the emphasis that falls inside the cut. */
internal fun Styled.annotated(from: Int = 0, to: Int = text.length): AnnotatedString = buildAnnotatedString {
    append(text.substring(from, to))
    for (span in spans) {
        val start = maxOf(span.start, from) - from
        val end = minOf(span.end, to) - from
        if (start >= end) continue
        val style = when (span.emphasis) {
            Emphasis.Bold -> SpanStyle(fontWeight = FontWeight.Bold)
            Emphasis.Italic -> SpanStyle(fontStyle = FontStyle.Italic)
        }
        addStyle(style, start, end)
    }
}

/**
 * The paginator's measure in the app: Compose's own text layout, with the same
 * styles the page draws with, so a page holds exactly the lines it was cut for.
 * An illustration takes a page of its own ([imageHeight] is the whole page), as
 * a printed novel's do.
 */
internal class ComposeMeasure(
    private val measurer: TextMeasurer,
    private val body: TextStyle,
    private val heading: TextStyle,
    private val imageHeight: Int,
) : BlockMeasure {
    override fun lines(block: Block, width: Int): List<Line> = when (block) {
        is Block.Image -> listOf(Line(0, 0, imageHeight))
        Block.Break -> listOf(Line(0, 0, height(AnnotatedString(SCENE_BREAK), body, width)))
        is Block.Heading -> textLines(block.text, heading, width)
        is Block.Paragraph -> textLines(block.text, body, width)
    }

    private fun height(text: AnnotatedString, style: TextStyle, width: Int): Int =
        measurer.measure(text, style, constraints = Constraints(maxWidth = width)).size.height

    private fun textLines(text: Styled, style: TextStyle, width: Int): List<Line> {
        val result = measurer.measure(text.annotated(), style, constraints = Constraints(maxWidth = width))
        return (0 until result.lineCount).map { i ->
            Line(
                result.getLineStart(i),
                result.getLineEnd(i),
                ceil(result.getLineBottom(i) - result.getLineTop(i)).toInt(),
            )
        }
    }
}
