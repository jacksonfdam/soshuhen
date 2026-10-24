package app.soshuhen.reader

import kotlin.test.Test
import kotlin.test.assertEquals

class XmlTest {
    private fun events(text: String) = XmlReader(text).events().map {
        when (it) {
            is XmlEvent.Start -> "<${it.name}${it.attributes.entries.joinToString("") { (k, v) -> " $k=$v" }}${if (it.selfClosing) "/" else ""}>"
            is XmlEvent.End -> "</${it.name}>"
            is XmlEvent.Text -> it.text
        }
    }.toList()

    @Test fun readsElementsAttributesAndText() {
        assertEquals(
            listOf("<a href=x y=it's>", "t", "<br/>", "</a>"),
            events("""<a href="x" y='it&apos;s'>t<br/></a>"""),
        )
    }

    @Test fun namespacePrefixesAreDropped() {
        assertEquals(listOf("<image href=p.png/>", "<title>", "x", "</title>"), events("""<svg:image xlink:href="p.png"/><dc:title>x</dc:title>"""))
    }

    @Test fun declarationsCommentsAndDoctypeAreSkipped() {
        assertEquals(listOf("<p>", "a", "</p>"), events("<?xml version=\"1.0\"?><!DOCTYPE html><!-- c --><p>a</p>"))
    }

    // Publishers' files are not always well formed; a stray < must not lose the rest.
    @Test fun aStrayLessThanIsText() {
        assertEquals(listOf("<p>", "1 < 2", "</p>"), events("<p>1 < 2</p>"))
    }
}
