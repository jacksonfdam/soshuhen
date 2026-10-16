"""J-Novel Club, driven by responses recorded from the live API."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.sources.base import ChapterUnavailable, NotConfigured, SignInRequired
from app.sources.jnovel_auth import JncSession, TokenKeeper
from app.sources.jnovelclub import JNovelClubSource, expires_at
from app.sources.net import CatalogueRow, SiteClient

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
PART_URL = "https://j-novel.club/read/the-apothecary-diaries-volume-16-part-1"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _source() -> JNovelClubSource:
    # client is never reached: these tests call the pure parsers.
    return JNovelClubSource(client=object(), now=lambda: NOW)


def test_search_offers_novels_only_best_first():
    found = _source().parse_search(json.loads(_read("jnovelclub_search.json")),
                                   ["The Apothecary Diaries"])
    assert found[0].title == "The Apothecary Diaries"
    assert found[0].source_url == "https://j-novel.club/series/the-apothecary-diaries"
    assert len(found) == 4
    assert {c.source_site for c in found} == {"jnovelclub"}
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_search_skips_manga():
    payload = {"series": [{"type": "MANGA", "slug": "x", "title": "The Apothecary Diaries"}]}
    assert _source().parse_search(payload, ["The Apothecary Diaries"]) == []


def test_parts_are_chapters_numbered_across_the_series():
    chapters = _source().parse_chapters(json.loads(_read("jnovelclub_aggregate.json")))
    assert len(chapters) == 216
    volume_16 = [c for c in chapters if c.volume == "16"]
    assert [c.number for c in volume_16] == [Decimal(n) for n in range(204, 217)]
    assert volume_16[0].url == PART_URL
    assert volume_16[0].title == "The Apothecary Diaries: Volume 16 Part 1"


def test_a_part_expires_from_its_volumes_publishing_date():
    chapters = _source().parse_chapters(json.loads(_read("jnovelclub_aggregate.json")))
    by_number = {c.number: c for c in chapters}
    # Volume 16 published 2026-05-29, on or after the 9th: the 15th of June.
    assert by_number[Decimal(205)].available_until == datetime(2026, 6, 15, 10, tzinfo=UTC)
    # A preview part never expires.
    assert by_number[Decimal(204)].available_until is None


def test_parts_not_launched_yet_are_not_listed():
    payload = {"volumes": [{
        "volume": {"number": 1, "publishing": "2027-01-01T00:00:00Z", "owned": False},
        "parts": [
            {"number": 1, "slug": "s-1", "title": "P1", "preview": True,
             "launch": "2026-10-01T00:00:00Z"},
            {"number": 2, "slug": "s-2", "title": "P2", "preview": False,
             "launch": "2026-10-20T00:00:00Z"},
        ],
    }]}
    assert [c.number for c in _source().parse_chapters(payload)] == [Decimal(1)]


def test_parts_of_an_owned_volume_never_expire():
    payload = {"volumes": [{
        "volume": {"number": 1, "publishing": "2026-05-29T05:00:00Z", "owned": True},
        "parts": [{"number": 1, "slug": "s-1", "title": "P1", "preview": False,
                   "launch": "2026-01-01T00:00:00Z"}],
    }]}
    assert _source().parse_chapters(payload)[0].available_until is None


@pytest.mark.parametrize(
    ("publishing", "expected"),
    [
        (datetime(2025, 9, 12, 5, tzinfo=UTC), datetime(2025, 10, 15, 10, tzinfo=UTC)),
        (datetime(2021, 2, 8, 5, tzinfo=UTC), datetime(2021, 2, 15, 10, tzinfo=UTC)),
        # 15 Feb 2026 is a Sunday: Monday the 16th.
        (datetime(2026, 1, 20, tzinfo=UTC), datetime(2026, 2, 16, 10, tzinfo=UTC)),
        # 15 Nov 2025 is a Saturday: Monday the 17th.
        (datetime(2025, 11, 3, tzinfo=UTC), datetime(2025, 11, 17, 10, tzinfo=UTC)),
        # December rolls into January of the next year.
        (datetime(2026, 12, 20, tzinfo=UTC), datetime(2027, 1, 15, 10, tzinfo=UTC)),
    ],
)
def test_expiry_follows_the_web_apps_rule(publishing, expected):
    assert expires_at(publishing) == expected


def test_a_part_body_keeps_its_text_and_illustrations():
    text = _source().parse_chapter(_read("jnovelclub_part.xhtml"), PART_URL)
    assert text.body.startswith("{{img:0}}<h1>Prologue</h1><p>In a world far, far away")
    assert text.body.count("<p>") == 305
    assert len(text.images) == 3
    assert text.images[0].headers == {"Referer": "https://j-novel.club/"}
    # The note asking readers not to build EPUBs is an HTML comment; it never
    # reaches the chapter.
    assert "build EPUBs" not in text.body


def _network(handler, keeper_factory):
    client = SiteClient(
        # A generous limit: these tests exercise status handling, not pacing.
        CatalogueRow(key="jnc-test", base_url="https://labs.j-novel.club",
                     rate_limit={"permits": 100, "period_seconds": 1}),
        transport=httpx.MockTransport(handler),
    )
    return JNovelClubSource(keeper=keeper_factory(client), client=client, now=lambda: NOW)


def _stored(token="saved"):
    async def load():
        return JncSession(token, datetime(2026, 10, 20, tzinfo=UTC))

    return lambda client: TokenKeeper(client, load_stored=load, now=lambda: NOW)


def _part_lookup(request):
    return httpx.Response(200, json={"id": "PRT-1", "slug": "x"})


async def test_fetch_sends_the_token_and_reads_the_part():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        return httpx.Response(200, text=_read("jnovelclub_part.xhtml"),
                              headers={"content-type": "application/xhtml+xml"})

    text = await _network(handler, _stored()).fetch_chapter(PART_URL)
    assert seen[-1].url.path == "/embed/v2/PRT-1/data.xhtml"
    assert seen[-1].headers["authorization"] == "Bearer saved"
    assert text.body.count("<p>") == 305


@pytest.mark.parametrize(
    ("status", "reason"),
    [(402, "purchase"), (403, "membership"), (410, "expired"), (451, "region")],
)
async def test_refusals_become_unavailable_with_the_reason(status, reason):
    def handler(request):
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        if request.url.path == "/app/v2/me":
            # The session is fine: the refusal is about the part itself.
            return httpx.Response(200, json={"level": "PREMIUM_MEMBER"})
        return httpx.Response(status, text="no")

    with pytest.raises(ChapterUnavailable, match=reason):
        await _network(handler, _stored()).fetch_chapter(PART_URL)


async def test_a_refused_stored_token_asks_for_a_new_sign_in():
    def handler(request):
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        return httpx.Response(401)

    with pytest.raises(NotConfigured, match="sign in again"):
        await _network(handler, _stored()).fetch_chapter(PART_URL)


async def test_env_credentials_sign_in_again_once_after_a_401():
    logins = 0
    embeds = 0

    def handler(request):
        nonlocal logins, embeds
        if request.url.path == "/app/v2/auth/login":
            logins += 1
            return httpx.Response(201, json={"id": f"tok-{logins}", "ttl": 1209600})
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        embeds += 1
        if request.headers["authorization"] == "Bearer tok-1":
            return httpx.Response(401)
        return httpx.Response(200, text=_read("jnovelclub_part.xhtml"))

    source = _network(
        handler, lambda c: TokenKeeper(c, login_name="me", password="pw", now=lambda: NOW)
    )
    await source.fetch_chapter(PART_URL)
    assert (logins, embeds) == (2, 2)


async def test_listing_works_without_a_sign_in():
    def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, text=_read("jnovelclub_aggregate.json"))

    source = _network(handler, lambda c: TokenKeeper(c, now=lambda: NOW))
    chapters = await source.list_chapters("https://j-novel.club/series/the-apothecary-diaries")
    assert len(chapters) == 216


@pytest.mark.parametrize("status", [403, 410])
async def test_a_refusal_from_a_dead_session_asks_for_a_sign_in_not_a_skip(status):
    # A token revoked on J-Novel Club's side answers like a refused part. Read
    # as the part's fault, every part in the batch would be skipped for good -
    # and pre-publication parts expire.
    def handler(request):
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        if request.url.path == "/app/v2/me":
            return httpx.Response(401)
        return httpx.Response(status, text="no")

    with pytest.raises(SignInRequired):
        await _network(handler, _stored()).fetch_chapter(PART_URL)


async def test_a_rejected_token_does_not_stop_discovery():
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        if "authorization" in request.headers:
            return httpx.Response(401)
        return httpx.Response(200, text=_read("jnovelclub_aggregate.json"))

    source = _network(handler, _stored())
    chapters = await source.list_chapters("https://j-novel.club/series/the-apothecary-diaries")
    assert len(chapters) == 216
    assert seen == ["Bearer saved", None]
