"""The prose contract sits beside the image one, and the registry tells them apart."""

import pytest

from app.sources import base


class Comic(base.Source):
    site = "comic-site"
    domains = ()

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def list_pages(self, chapter_url, *, language="en"):
        return []


class Prose(base.ProseSource):
    site = "prose-site"
    domains = ()

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        return base.ChapterText(title=None, body="<p>x</p>", images=[])


class DuckTyped:
    """The shape the download tests' fakes take: no base class, no kind."""

    site = "duck"
    domains = ()


@pytest.fixture
def registry():
    base.install_registry(
        {
            "comic-site": base.RegisteredSource(Comic(), "https://comic.test"),
            "prose-site": base.RegisteredSource(Prose(), "https://prose.test"),
            "duck": base.RegisteredSource(DuckTyped(), "https://duck.test"),
        }
    )
    yield
    base.install_registry({})


def test_each_contract_declares_its_kind():
    assert Comic.kind == "comic"
    assert Prose.kind == "prose"
    assert base.kind_of(DuckTyped()) == "comic"


def test_all_sources_filters_by_kind(registry):
    assert {s.site for s in base.all_sources(kind="prose")} == {"prose-site"}
    assert {s.site for s in base.all_sources(kind="comic")} == {"comic-site", "duck"}
    assert len(base.all_sources()) == 3


def test_the_narrowed_getters_refuse_the_other_kind(registry):
    assert isinstance(base.get_prose_source("prose-site"), Prose)
    assert isinstance(base.get_comic_source("comic-site"), Comic)
    with pytest.raises(TypeError, match="prose-site is a prose source"):
        base.get_comic_source("prose-site")
    with pytest.raises(TypeError, match="comic-site is a comic source"):
        base.get_prose_source("comic-site")
    with pytest.raises(ValueError, match="unknown source site"):
        base.get_prose_source("nowhere")


async def test_a_prose_source_returns_chapter_text():
    text = await Prose().fetch_chapter("https://prose.test/c/1")
    assert text == base.ChapterText(title=None, body="<p>x</p>", images=[])
