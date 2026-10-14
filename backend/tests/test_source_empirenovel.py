"""Golden tests for EmpireNovel, driven by responses recorded through FlareSolverr."""

import json
from decimal import Decimal
from pathlib import Path

from app.sources.empirenovel import EmpireNovelSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
BOOK = "shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you"


def _source() -> EmpireNovelSource:
    # client is never reached: every test here calls a pure parser directly.
    return EmpireNovelSource(client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_reads_the_typeahead_payload():
    payload = json.loads(_read("empirenovel_search.json"))
    found = _source().parse_search(payload, ["The Divine Nine-Dragon Cauldron"])
    assert len(found) == 55
    assert found[0].title == "The Divine Nine-Dragon Cauldron"
    assert found[0].source_url == "https://www.empirenovel.com/novel/the-divine-nine-dragon-cauldron"
    assert found[0].cover_url == (
        "https://www.empirenovel.com/uploads/novel/the-divine-nine-dragon-cauldron/"
        "cover/cover_250x350.jpg"
    )


def test_other_names_arrive_as_one_string_not_a_list():
    payload = json.loads(_read("empirenovel_search.json"))
    found = _source().parse_search(payload, ["The Divine Nine-Dragon Cauldron"])
    assert found[0].alt_titles == ["九龙神鼎"]

    def names(value):
        item = {"name": "T", "slug": "t", "otherNames": value}
        return _source().parse_search([item], ["T"])[0].alt_titles

    assert names("A, B") == ["A", "B"]
    assert names(None) == []
    assert names(["A", "", 3]) == ["A"]


def test_the_first_chapter_is_read_off_the_book_page():
    first = _source().parse_first_chapter(_read("empirenovel_book.html"))
    assert first == f"https://www.empirenovel.com/novel/{BOOK}/1"


def test_the_dropdown_lists_every_chapter_numbered_by_url():
    chapters = _source().parse_chapters(_read("empirenovel_chapters.html"))
    assert len(chapters) == 195
    assert chapters[0].number == Decimal(1)
    assert chapters[0].url == f"https://www.empirenovel.com/novel/{BOOK}/1"
    assert chapters[-1].number == Decimal(195)


def test_a_duplicated_number_keeps_its_first_address():
    html = (
        '<select id="chapter-list">'
        '<option value="/novel/x/2">Chapter 2</option>'
        '<option value="/novel/x/02">Chapter 02</option>'
        '<option value="/novel/x/1">Chapter 1</option>'
        "</select>"
    )
    chapters = _source().parse_chapters(html)
    assert [(c.number, c.url) for c in chapters] == [
        (Decimal(1), "https://www.empirenovel.com/novel/x/1"),
        (Decimal(2), "https://www.empirenovel.com/novel/x/02"),
    ]


def test_a_chapter_keeps_its_paragraphs_and_drops_the_reader_chrome():
    text = _source().parse_chapter(
        _read("empirenovel_chapter.html"), f"https://www.empirenovel.com/novel/{BOOK}/1"
    )
    assert text.body.count("<p>") == 112
    assert "chapter-right" not in text.body
    assert text.images == []
