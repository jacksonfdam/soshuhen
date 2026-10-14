"""clean_chapter_html: whatever a site serves, the output is XHTML an EPUB can carry."""

from xml.etree import ElementTree as ET

import pytest

from app.sources.base import ChapterUnavailable
from app.sources.prose import clean_chapter_html

BASE = "https://site.test/n/1/2"


def _parses(body: str) -> ET.Element:
    return ET.fromstring(f'<body xmlns="http://www.w3.org/1999/xhtml">{body}</body>')


def test_allowlisted_formatting_survives():
    body, _ = clean_chapter_html(
        "<p>One <em>two</em> <strong>three</strong></p><hr><blockquote>q</blockquote>", BASE
    )
    assert body == "<p>One <em>two</em> <strong>three</strong></p><hr/><blockquote>q</blockquote>"
    _parses(body)


def test_scripts_styles_and_attributes_are_dropped():
    body, _ = clean_chapter_html(
        '<p onclick="steal()" style="color:red" class="x">Hi</p>'
        "<script>alert(1)</script><style>p{}</style><iframe src='ad'></iframe>",
        BASE,
    )
    assert body == "<p>Hi</p>"


def test_unknown_tags_are_unwrapped_and_their_text_kept():
    body, _ = clean_chapter_html("<p>a <span><font>b</font></span> <a href='/x'>c</a></p>", BASE)
    assert body == "<p>a b c</p>"


def test_a_div_holding_only_text_becomes_a_paragraph():
    body, _ = clean_chapter_html("<div><div>First</div><div>Second</div></div>", BASE)
    assert body == "<p>First</p><p>Second</p>"


def test_empty_and_nbsp_paragraphs_are_removed():
    body, _ = clean_chapter_html("<p>&nbsp;</p><p> </p><p>Kept</p>", BASE)
    assert body == "<p>Kept</p>"


def test_entities_come_out_as_xml():
    body, _ = clean_chapter_html("<p>Tom &amp; Jerry &lt;3 &hellip;</p>", BASE)
    assert body == "<p>Tom &amp; Jerry &lt;3 …</p>"
    _parses(body)


def test_control_characters_are_removed_so_the_xml_parses():
    body, _ = clean_chapter_html("<p>bad\x0bchar\x00s</p>", BASE)
    assert body == "<p>badchars</p>"
    _parses(body)


def test_images_become_ordered_placeholders_with_absolute_urls():
    body, images = clean_chapter_html(
        '<p>Look <img src="/img/a.png"></p><img data-src="https://cdn.test/b.jpg">', BASE
    )
    assert body == "<p>Look {{img:0}}</p>{{img:1}}"
    assert images == ["https://site.test/img/a.png", "https://cdn.test/b.jpg"]


def test_a_body_with_nothing_left_is_unavailable():
    with pytest.raises(ChapterUnavailable):
        clean_chapter_html("<script>x</script><p>&nbsp;</p>", BASE)


def test_bare_top_level_text_is_wrapped_in_a_paragraph():
    body, _ = clean_chapter_html("Loose text<br>more<p>Para</p>", BASE)
    assert body == "<p>Loose text<br/>more</p><p>Para</p>"
