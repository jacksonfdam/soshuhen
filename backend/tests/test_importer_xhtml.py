"""PDF page text into the XHTML body of a chapter EPUB.

Extracted text is laid out for paper: every line breaks where the page did, and
page numbers and running headers sit in the middle of sentences. A reader shows
whatever survives this step, so what it drops and joins is what the reader sees.
"""

import xml.etree.ElementTree as ET

from app.importer.pdf import PdfEntry
from app.importer.xhtml import entries_to_body


def entry(title: str, *pages: str, images: list[bytes] | None = None) -> PdfEntry:
    return PdfEntry(title=title, pages=list(pages), images=images or [])


def paragraphs(body: str) -> list[str]:
    root = ET.fromstring(f"<div>{body}</div>")
    return [p.text or "" for p in root.iter("p")]


def test_paragraphs_are_joined_across_wrapped_lines():
    body, _ = entry_body(
        "The road went on for a long\nway, and the boy kept walking.\n\nNight fell."
    )

    assert paragraphs(body) == ["The road went on for a long way, and the boy kept walking.", "Night fell."]


def test_a_finished_sentence_followed_by_a_capital_starts_a_new_paragraph():
    body, _ = entry_body("He stopped.\nThen he turned around.")

    assert paragraphs(body) == ["He stopped.", "Then he turned around."]


def test_a_paragraph_continues_across_a_page_break():
    body, _ = entries_to_body([entry("Chapter 1", "It was a long\n", "road home.")])

    assert paragraphs(body) == ["It was a long road home."]


def test_page_numbers_and_running_headers_are_dropped():
    pages = [f"Tsuki ga Michibiku\nLine {n} of the story.\n{n}" for n in range(1, 5)]

    body, _ = entries_to_body([entry("Chapter 1", *pages)])

    assert paragraphs(body) == [f"Line {n} of the story." for n in range(1, 5)]


def test_page_n_lines_are_dropped():
    body, _ = entry_body("A sentence.\nPage 12\nAnother sentence.")

    assert paragraphs(body) == ["A sentence.", "Another sentence."]


def test_markup_characters_are_escaped():
    body, _ = entry_body("a < b & c")

    assert "a &lt; b &amp; c" in body


def test_each_entry_title_is_a_heading():
    body, _ = entries_to_body([entry("Cover", "x"), entry("Chapter 1 Start", "Text.")])

    root = ET.fromstring(f"<div>{body}</div>")
    assert [h.text for h in root.iter("h2")] == ["Cover", "Chapter 1 Start"]


def test_images_are_referenced_in_order():
    body, images = entries_to_body(
        [entry("Cover", "x", images=[b"one"]), entry("Chapter 1", "y", images=[b"two"])]
    )

    assert images == [b"one", b"two"]
    assert body.index("{{img:0}}") < body.index("{{img:1}}")


def test_body_is_well_formed():
    body, _ = entry_body('Quotes "here" & <tags> and\x0ccontrol chars.')

    ET.fromstring(f"<div>{body}</div>")


def entry_body(text: str) -> tuple[str, list[bytes]]:
    body, images = entries_to_body([entry("Chapter 1", text)])
    # The heading is tested on its own; these tests are about the paragraphs.
    return body.split("</h2>", 1)[1], images


def test_without_own_heading_only_folded_front_matter_is_headed():
    # write_epub heads the chapter with its own title; a second heading would repeat it.
    body, _ = entries_to_body([entry("Cover", "x"), entry("Chapter 1", "Text.")], own_heading=False)

    root = ET.fromstring(f"<div>{body}</div>")
    assert [h.text for h in root.iter("h2")] == ["Cover"]


def test_a_literal_image_placeholder_in_the_text_is_not_an_image():
    body, images = entry_body("He wrote {{img:0}} on the wall.")

    assert images == []
    assert "{{img:0}}" not in body
