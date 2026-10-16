"""The J-Novel Club library, read from a payload built from its message definitions.

No live library page has been seen: the account this was built with owned
nothing. The shape follows J-Novel Club's LibraryBook and Download messages
and the field names the clients that download owned books rely on.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.sources.base import SignInRequired
from app.sources.jnovel_auth import JncSession, TokenKeeper
from app.sources.jnovelclub import (
    JNovelClubSource,
    OwnedVolume,
    parse_library,
    parse_part_ranges,
)
from app.sources.net import CatalogueRow, SiteClient

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def _book(number, *, slug="the-apothecary-diaries", status="OWNED", downloads=None):
    return {
        "id": f"LIB-{number}",
        "volume": {"id": f"VOL-{number}", "number": number, "title": f"Volume {number}"},
        "serie": {"slug": slug, "title": "The Apothecary Diaries"},
        "status": status,
        "lastUpdated": "2026-09-01T12:00:00Z",
        "downloads": downloads
        if downloads is not None
        else [
            {"link": "https://cdn.example/v.pdf", "type": "PDF", "label": "PDF"},
            {"link": f"https://cdn.example/v{number}.epub?sig=x", "type": "EPUB", "label": "EPUB"},
        ],
    }


def test_a_library_page_becomes_owned_volumes():
    volumes, last, _ = parse_library(
        {"books": [_book(16)], "pagination": {"limit": 100, "skip": 0, "lastPage": True}}
    )
    assert last is True
    assert volumes == [
        OwnedVolume(
            series_slug="the-apothecary-diaries",
            volume_id="VOL-16",
            number=Decimal(16),
            title="Volume 16",
            status="owned",
            last_updated=datetime(2026, 9, 1, 12, tzinfo=UTC),
            epub_link="https://cdn.example/v16.epub?sig=x",
        )
    ]


def test_a_preorder_and_a_book_without_an_epub_are_kept_but_flagged():
    volumes, _, _ = parse_library(
        {"books": [_book(17, status="PREORDER"), _book(18, downloads=[])]}
    )
    assert [(v.number, v.status, v.epub_link) for v in volumes] == [
        (Decimal(17), "preorder", "https://cdn.example/v17.epub?sig=x"),
        (Decimal(18), "owned", None),
    ]


def test_an_empty_library_is_one_last_page():
    assert parse_library({"books": [], "pagination": {"lastPage": True}}) == ([], True, 0)


def test_part_ranges_come_from_the_aggregate():
    ranges = parse_part_ranges(json.loads((FIXTURES / "jnovelclub_aggregate.json").read_text()))
    assert ranges[Decimal(16)] == (Decimal(204), Decimal(216))
    assert ranges[Decimal(1)][0] == Decimal(1)


def _source(handler, keeper_factory):
    client = SiteClient(
        CatalogueRow(key="jnc-lib-test", base_url="https://labs.j-novel.club",
                     rate_limit={"permits": 100, "period_seconds": 1}),
        transport=httpx.MockTransport(handler),
    )
    return JNovelClubSource(keeper=keeper_factory(client), client=client, now=lambda: NOW)


def _stored(client):
    async def load():
        return JncSession("saved", datetime(2026, 10, 20, tzinfo=UTC))

    return TokenKeeper(client, load_stored=load, now=lambda: NOW)


async def test_the_library_is_paged_until_the_last_page():
    seen = []

    def handler(request):
        seen.append(int(request.url.params["skip"]))
        last = request.url.params["skip"] == "1"
        number = 1 if not last else 2
        return httpx.Response(
            200, json={"books": [_book(number)], "pagination": {"lastPage": last}}
        )

    volumes = await _source(handler, _stored).library()
    assert seen == [0, 1]
    assert [v.number for v in volumes] == [Decimal(1), Decimal(2)]


async def test_reading_the_library_needs_a_sign_in():
    def handler(request):
        raise AssertionError("no request without a token")

    with pytest.raises(SignInRequired):
        await _source(handler, lambda c: TokenKeeper(c, now=lambda: NOW)).library()


async def test_a_rejected_token_on_the_library_asks_for_a_sign_in():
    with pytest.raises(SignInRequired):
        await _source(lambda request: httpx.Response(401), _stored).library()


async def test_a_volume_is_fetched_without_the_token():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"epub-bytes")

    data = await _source(handler, _stored).fetch_volume("https://cdn.example/v16.epub?sig=x")
    assert data == b"epub-bytes"
    assert "authorization" not in seen[0].headers
    assert seen[0].url.host == "cdn.example"


def test_a_malformed_entry_is_skipped_not_fatal():
    payload = {"books": [
        {"volume": {"id": 99, "number": "not-a-number"}, "serie": {"slug": "s"}},
        _book(16),
        {"volume": {"id": 123, "number": 2}, "serie": {"slug": "s"}, "lastUpdated": 5},
    ], "pagination": {"lastPage": True}}
    volumes, _, raw = parse_library(payload)
    assert raw == 3
    assert [v.number for v in volumes] == [Decimal(16), Decimal(2)]
    # An id that arrives as a number is still stored as text.
    assert volumes[1].volume_id == "123"
    assert volumes[1].last_updated is None


async def test_paging_counts_every_entry_not_only_the_parsed_ones():
    seen = []

    def handler(request):
        skip = int(request.url.params["skip"])
        seen.append(skip)
        if skip == 0:
            # A whole page the parser cannot use must not end the paging.
            return httpx.Response(200, json={
                "books": [{"volume": {}, "serie": {}}] * 2, "pagination": {"lastPage": False},
            })
        return httpx.Response(200, json={"books": [_book(7)], "pagination": {"lastPage": True}})

    volumes = await _source(handler, _stored).library()
    assert seen == [0, 2]
    assert [v.number for v in volumes] == [Decimal(7)]
