"""Golden tests for LoLoBun, driven by recorded responses."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.base import ChapterUnavailable
from app.sources.lolobun import LolobunSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def _source() -> LolobunSource:
    # client is never reached: every test here calls a pure parser directly.
    return LolobunSource(client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_offers_novels_only():
    payload = json.loads(_read("lolobun_search.json"))
    found = _source().parse_search(payload, ["Shut up, Evil Dragon"])
    assert found
    assert all(c.source_url.startswith("https://www.lolobun.com/n/") for c in found)
    assert {c.source_site for c in found} == {"lolobun"}
    # The same title exists as a comic (/c/20103) in the recorded payload.
    assert not any("/c/" in c.source_url for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_chapters_are_numbered_by_catalogue_position():
    chapters = _source().parse_chapters(_read("lolobun_book.html"))
    assert len(chapters) == 589
    assert [c.number for c in chapters[:3]] == [Decimal(1), Decimal(2), Decimal(3)]
    assert chapters[0].url == "https://www.lolobun.com/n/5320143/7123286"
    assert chapters[0].title == "Chapter 1: The Brave is Coming to Attack the City! (Part 1)"
    # Spelled-out numbers in the title do not matter; position does.
    assert chapters[2].title.startswith("Chapter Three")
    assert chapters[-1].number == Decimal(589)


def test_volumes_travel_with_their_chapters():
    chapters = _source().parse_chapters(_read("lolobun_book.html"))
    assert chapters[0].volume == "Volume One: Twin Shining Stars"


def test_a_free_chapter_parses_to_paragraphs():
    text = _source().parse_chapter(
        _read("lolobun_chapter.html"), "https://www.lolobun.com/n/5320143/7123286"
    )
    assert text.body.startswith("<p>The autumn wind blows coldly.</p>")
    assert text.body.count("<p>") == 63
    assert text.images == []


def test_a_locked_chapter_is_unavailable_not_a_teaser():
    with pytest.raises(ChapterUnavailable, match="locked"):
        _source().parse_chapter(
            _read("lolobun_locked.html"), "https://www.lolobun.com/n/5320143/7124349"
        )
