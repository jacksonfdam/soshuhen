"""Which volume Komga reading amounts to, and what each list may be sent."""

import json
from decimal import Decimal

import httpx
import pytest

from app.handlers.volume_progress import VolumeRow, furthest_volume, pushable_volume
from app.komga.client import KomgaBook
from app.providers.anilist import AniListSource
from app.providers.base import WriteRefused
from app.providers.mal import MyAnimeListSource
from app.providers.mangabaka import MangaBakaSource


def _book(book_id, completed=True):
    return KomgaBook(id=book_id, series_id="S", name=book_id, path=f"/m/{book_id}",
                     completed=completed, page=0)


V15 = VolumeRow(Decimal(15), Decimal(193), Decimal(203), "V15")
V16 = VolumeRow(Decimal(16), Decimal(204), Decimal(216), "V16")


def _parts(first, last, *, read=True, missing_book=None, missing_row=None):
    rows = {}
    for n in range(first, last + 1):
        if n == missing_row:
            continue
        rows[Decimal(n)] = None if n == missing_book else f"P{n}"
    books = [_book(f"P{n}", completed=read) for n in range(first, last + 1)]
    return rows, books


def test_a_finished_volume_book_is_read():
    assert furthest_volume([_book("V16")], [V15, V16], {}) == (16, Decimal(216))


def test_an_unfinished_volume_book_is_not():
    assert furthest_volume([_book("V16", completed=False)], [V16], {}) == (None, None)


def test_every_part_finished_reads_the_volume():
    rows, books = _parts(204, 216)
    assert furthest_volume(books, [V16], rows) == (16, Decimal(216))


def test_one_unread_part_keeps_the_volume_unread():
    rows, books = _parts(204, 216)
    books[-1] = _book("P216", completed=False)
    assert furthest_volume(books, [V16], rows) == (None, None)


def test_a_part_never_downloaded_keeps_the_volume_unread():
    rows, books = _parts(204, 216, missing_book=210)
    assert furthest_volume(books, [V16], rows) == (None, None)


def test_a_part_never_discovered_keeps_the_volume_unread():
    rows, books = _parts(204, 216, missing_row=210)
    assert furthest_volume(books, [V16], rows) == (None, None)


def test_a_volume_without_a_known_range_needs_its_book():
    no_range = VolumeRow(Decimal(16), None, None, "V16")
    rows, books = _parts(204, 216)
    assert furthest_volume(books, [no_range], rows) == (None, None)


def test_the_furthest_wins_and_a_half_volume_counts_as_the_one_below():
    half = VolumeRow(Decimal("15.5"), None, Decimal(210), "V15.5")
    assert furthest_volume([_book("V15"), _book("V15.5")], [V15, half], {}) == (15, Decimal(210))


def test_comics_have_no_volumes():
    assert furthest_volume([_book("C1")], [], {Decimal(1): "C1"}) == (None, None)


def test_pushable_volume():
    assert pushable_volume(16, 20, 3) == 16
    assert pushable_volume(16, 12, 3) == 12  # capped at the list's total
    assert pushable_volume(16, None, 3) == 16  # no total, no cap
    assert pushable_volume(16, 0, None) == 16  # 0 is unknown, not a cap
    assert pushable_volume(16, None, 16) is None  # not forward
    assert pushable_volume(None, 20, 3) is None


# --- provider request bodies -------------------------------------------------


def _recorder(status=200, body=None):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {})

    return seen, httpx.MockTransport(handler)


async def test_mal_sends_volumes_only_when_given():
    seen, transport = _recorder()
    async with httpx.AsyncClient(transport=transport) as client:
        await MyAnimeListSource(client).push_progress("t", "1", 12)
        await MyAnimeListSource(client).push_progress("t", "1", 12, volume=3)
    assert dict(httpx.QueryParams(seen[0].content.decode())) == {"num_chapters_read": "12"}
    assert dict(httpx.QueryParams(seen[1].content.decode())) == {
        "num_chapters_read": "12", "num_volumes_read": "3",
    }


async def test_anilist_never_sends_a_null_volume():
    body = {"data": {"SaveMediaListEntry": {"id": 1, "progress": 12}}}
    seen, transport = _recorder(body=body)
    async with httpx.AsyncClient(transport=transport) as client:
        await AniListSource(client).push_progress("t", "7", 12)
        await AniListSource(client).push_progress("t", "7", 12, volume=3)
    first, second = (json.loads(r.content) for r in seen)
    assert first["variables"] == {"mediaId": 7, "progress": 12}
    assert "progressVolumes" not in first["query"]
    assert second["variables"] == {"mediaId": 7, "progress": 12, "progressVolumes": 3}


async def test_mangabaka_sends_volume_progress():
    seen, transport = _recorder(body={"status": 200, "data": []})
    async with httpx.AsyncClient(transport=transport) as client:
        await MangaBakaSource(client).push_progress("k", "5", 12, volume=3)
    assert json.loads(seen[0].content) == [
        {"series_id": 5, "progress_chapter": 12, "progress_volume": 3}
    ]


@pytest.mark.parametrize("status", [400, 422])
async def test_a_refused_write_says_so(status):
    _, transport = _recorder(status=status)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(WriteRefused):
            await MyAnimeListSource(client).push_progress("t", "1", 12, volume=99)
        with pytest.raises(WriteRefused):
            await MangaBakaSource(client).push_progress("k", "5", 12, volume=99)


async def test_an_anilist_graphql_error_is_a_refusal():
    _, transport = _recorder(body={"errors": [{"message": "validation"}], "data": None})
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(WriteRefused):
            await AniListSource(client).push_progress("t", "7", 12, volume=99)
