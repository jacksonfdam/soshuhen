"""Golden tests for Gadgetized Panda, driven by responses recorded from its WordPress API.

The post lists and categories are real. The chapter fixtures keep the shape of a
real post - its Gutenberg blocks, the star scene breaks, the footer - with the
novel's text replaced by stand-in lines.
"""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.sources.base import ChapterUnavailable
from app.sources.gadgetizedpanda import GadgetizedPandaSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
CATEGORY = "https://gadgetizedpanda.net/category/translation/spacemob/geek-mob/"
CHAPTER = "https://gadgetizedpanda.net/2023/07/26/geek-mob-mercenary-chapter-7/"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _json(name: str):
    return json.loads(_read(name))


class FakeClient:
    """Answers by path, records every request, and never touches the network."""

    def __init__(self, routes: dict[str, httpx.Response]) -> None:
        self.routes = routes
        self.requests: list[tuple[str, dict]] = []

    async def get(self, url: str, params=None, headers=None) -> httpx.Response:
        params = dict(params or {})
        self.requests.append((url, params))
        key = url if "page" not in params else f"{url}#{params['page']}"
        response = self.routes.get(key)
        if response is None:
            return httpx.Response(404, json={"code": "rest_no_route"}, request=_request(url))
        return response


def _request(url: str) -> httpx.Request:
    return httpx.Request("GET", url if url.startswith("http") else f"https://x{url}")


def _ok(url: str, *, json_body=None, text=None, headers=None) -> httpx.Response:
    if json_body is not None:
        return httpx.Response(200, json=json_body, headers=headers, request=_request(url))
    return httpx.Response(200, text=text, headers=headers, request=_request(url))


def _source(client=None) -> GadgetizedPandaSource:
    return GadgetizedPandaSource(client=client or object())


# search


def test_search_reads_category_names():
    found = _source().parse_search(
        _json("gadgetizedpanda_category_search.json"), ["web novel geek mob"]
    )
    assert [c.title for c in found] == ["web novel geek mob", "light novel geek mob"]
    assert found[0].source_url == CATEGORY
    assert found[0].chapter_count == 145
    assert found[0].source_site == "gadgetizedpanda"


async def test_search_asks_every_title_once_and_merges_the_answers():
    payload = _json("gadgetizedpanda_category_search.json")
    client = FakeClient({"/wp-json/wp/v2/categories": _ok("/c", json_body=payload)})
    found = await _source(client).search(["Geek Mob", "Geek Mob", "geek mob mercenary"])
    assert [params["search"] for _, params in client.requests] == ["Geek Mob", "geek mob mercenary"]
    # The same category from two queries is one candidate.
    assert len(found) == 2


# list_chapters


def test_a_category_address_names_its_slug_however_deep_it_is_nested():
    source = _source()
    assert source.category_slug(CATEGORY) == "geek-mob"
    assert source.category_slug("https://gadgetizedpanda.net/category/geek-mob") == "geek-mob"
    with pytest.raises(ChapterUnavailable):
        source.category_slug(CHAPTER)


def test_chapters_are_numbered_from_their_titles_and_other_posts_are_skipped():
    posts = _json("gadgetizedpanda_posts_1.json") + _json("gadgetizedpanda_posts_2.json")
    chapters = _source().parse_chapters(posts)
    # 145 posts: 143 chapters, the illustration post and the index page.
    assert len(chapters) == 143
    assert chapters[0].number == Decimal(1)
    assert chapters[0].url == "https://gadgetizedpanda.net/2023/07/23/geek-mob-mercenary-chapter-1/"
    assert chapters[-1].number == Decimal(143)
    assert [c.number for c in chapters] == [Decimal(n) for n in range(1, 144)]


def _post(title: str, slug: str) -> dict:
    return {"slug": slug, "link": f"https://gadgetizedpanda.net/{slug}/", "title": {"rendered": title}}


def test_volumes_and_parts_fall_back_to_position():
    posts = [
        _post("Novel Volume 1 Chapter 1 part 1", "v1c1p1"),
        _post("Novel Volume 1 Chapter 1 part 2", "v1c1p2"),
        _post("Novel Volume 2 Chapter&nbsp;1", "v2c1"),
    ]
    chapters = _source().parse_chapters(posts)
    # Printed numbers repeat across parts and volumes, and two chapters
    # numbered 1 would collide on (series, number).
    assert [(c.number, c.volume) for c in chapters] == [
        (Decimal(1), "1"),
        (Decimal(2), "1"),
        (Decimal(3), "2"),
    ]


async def test_list_chapters_pages_through_the_category_by_its_total_pages_header():
    client = FakeClient(
        {
            "/wp-json/wp/v2/categories": _ok(
                "/c", json_body=_json("gadgetizedpanda_category.json")
            ),
            "/wp-json/wp/v2/posts#1": _ok(
                "/p",
                json_body=_json("gadgetizedpanda_posts_1.json"),
                headers={"X-WP-TotalPages": "2"},
            ),
            "/wp-json/wp/v2/posts#2": _ok(
                "/p",
                json_body=_json("gadgetizedpanda_posts_2.json"),
                headers={"X-WP-TotalPages": "2"},
            ),
        }
    )
    chapters = await _source(client).list_chapters(CATEGORY)
    assert len(chapters) == 143
    category_params = client.requests[0][1]
    assert category_params["slug"] == "geek-mob"
    pages = [params for url, params in client.requests if url.endswith("/posts")]
    assert [p["page"] for p in pages] == [1, 2]
    assert all(p["categories"] == 30 for p in pages)


async def test_an_unknown_category_is_unavailable():
    client = FakeClient({"/wp-json/wp/v2/categories": _ok("/c", json_body=[])})
    with pytest.raises(ChapterUnavailable):
        await _source(client).list_chapters(CATEGORY)


# fetch_chapter


def test_a_chapter_keeps_the_story_and_drops_the_translator_footer():
    post = _json("gadgetizedpanda_chapter.json")[0]
    text = _source().parse_chapter(post["content"]["rendered"], CHAPTER)
    assert "The first paragraph of a stand-in chapter." in text.body
    assert "The last paragraph of the story." in text.body
    assert "★★★" in text.body
    for footer in ("TLNOTE", "Previous Chapters", "Ko-Fi", "Donation"):
        assert footer not in text.body
    # The Ko-fi button is the only image, and it sits in the footer.
    assert text.images == []


async def test_fetch_chapter_reads_the_post_through_the_api():
    client = FakeClient(
        {"/wp-json/wp/v2/posts": _ok("/p", json_body=_json("gadgetizedpanda_chapter.json"))}
    )
    text = await _source(client).fetch_chapter(CHAPTER)
    assert client.requests[0][1]["slug"] == "geek-mob-mercenary-chapter-7"
    assert "The last paragraph of the story." in text.body
    assert "Donation" not in text.body


async def test_fetch_chapter_falls_back_to_the_page_when_the_api_refuses():
    client = FakeClient(
        {
            "/wp-json/wp/v2/posts": httpx.Response(
                401, json={"code": "rest_login_required"}, request=_request("/p")
            ),
            CHAPTER: _ok(CHAPTER, text=_read("gadgetizedpanda_chapter.html")),
        }
    )
    text = await _source(client).fetch_chapter(CHAPTER)
    assert "The first paragraph of a stand-in chapter." in text.body
    for chrome in ("Recent Posts", "Other Novel", "Posted in", "Donation"):
        assert chrome not in text.body


async def test_a_post_the_api_does_not_know_falls_back_and_a_missing_page_is_unavailable():
    client = FakeClient({"/wp-json/wp/v2/posts": _ok("/p", json_body=[])})
    with pytest.raises(ChapterUnavailable):
        await _source(client).fetch_chapter(CHAPTER)
    assert [url for url, _ in client.requests] == ["/wp-json/wp/v2/posts", CHAPTER]


def test_a_page_without_post_content_is_unavailable():
    with pytest.raises(ChapterUnavailable):
        _source().parse_chapter_page("<html><body><p>Not found</p></body></html>", CHAPTER)
