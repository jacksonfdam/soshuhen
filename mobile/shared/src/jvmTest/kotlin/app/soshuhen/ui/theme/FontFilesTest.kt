package app.soshuhen.ui.theme

import java.awt.Font
import java.awt.font.FontRenderContext
import java.io.File
import java.nio.ByteBuffer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FontFilesTest {
    private val fonts = File("src/commonMain/composeResources/font").listFiles()!!.filter { it.extension == "ttf" }

    private fun tables(file: File): Set<String> {
        val bytes = ByteBuffer.wrap(file.readBytes())
        val count = bytes.getShort(4).toInt()
        return (0 until count).map { i ->
            val at = 12 + i * 16
            String(ByteArray(4) { bytes.get(at + it) }, Charsets.US_ASCII)
        }.toSet()
    }

    // Android 11 and earlier draw a variable file's lighter weights with the
    // spaces collapsed, so every weight ships as its own static file.
    @Test fun everyBundledFontIsStatic() {
        assertEquals(8, fonts.size)
        for (file in fonts) assertFalse("fvar" in tables(file), "${file.name} is a variable font")
    }

    @Test fun everyBundledFontKeepsItsSpaces() {
        val context = FontRenderContext(null, true, true)
        for (file in fonts) {
            val font = Font.createFont(Font.TRUETYPE_FONT, file).deriveFont(13f)
            val spaced = font.getStringBounds("Plan to read", context).width
            val joined = font.getStringBounds("Plantoread", context).width
            assertTrue(spaced > joined, "${file.name} sets spaces as nothing")
        }
    }
}
