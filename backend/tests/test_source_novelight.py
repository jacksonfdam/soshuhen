"""Golden tests for Novelight, driven by recorded responses."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.base import ChapterUnavailable
from app.sources.novelight import NovelightSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
CHAPTER_URL = "https://novelight.net/book/chapter/178702"


def _source() -> NovelightSource:
    # client is never reached: every test here calls a pure parser directly.
    return NovelightSource(client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_parses_the_catalogue_grid():
    found = _source().parse_search(_read("novelight_search.html"), ["Shut Up, Malevolent Dragon"])
    assert len(found) == 7
    assert {c.source_site for c in found} == {"novelight"}
    assert found[0].source_url == (
        "https://novelight.net/book/"
        "shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you"
    )
    assert found[0].cover_url.startswith("https://novelight.net/media/")
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_the_book_id_is_read_from_the_page_script():
    assert _source().parse_book_id(_read("novelight_book.html")) == "403"


def test_chapters_run_oldest_first_numbered_by_position():
    html = json.loads(_read("novelight_chapters.json"))["html"]
    chapters = _source().parse_chapters(html)
    assert len(chapters) == 74
    assert chapters[0].number == Decimal(1)
    assert chapters[0].url == "https://novelight.net/book/chapter/178702"
    assert chapters[0].title == "The Beginning"
    assert chapters[-1].number == Decimal(74)
    assert chapters[-1].url == "https://novelight.net/book/chapter/217220"
    assert chapters[-1].title == "Negotiation"


def test_a_chapter_drops_the_ads_and_keeps_every_paragraph():
    content = json.loads(_read("novelight_chapter.json"))["content"]
    text = _source().parse_chapter(content, CHAPTER_URL)
    assert text.body.startswith(
        "<p>Deruo was, to put it simply, a rather unimpressive person.</p>"
    )
    assert "script" not in text.body
    assert "advertisment" not in text.body
    assert text.body.count("<p>") == 56


def test_a_locked_chapter_is_unavailable():
    content = json.loads(_read("novelight_locked.json"))["content"]
    with pytest.raises(ChapterUnavailable, match="locked"):
        _source().parse_chapter(content, CHAPTER_URL)
