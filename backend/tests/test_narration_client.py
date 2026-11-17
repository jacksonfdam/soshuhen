"""The narrator client against a stub transport: no service, no network."""

import httpx
import pytest

from app.reader.narration import NarratorFailed, transcribe

TRANSCRIPT = {
    "engine": "fake",
    "language": "en",
    "width": 10,
    "height": 20,
    "panels": [{"box": [0, 0, 10, 20], "blocks": [{"box": [1, 1, 5, 5], "text": "Hello."}]}],
}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_the_page_is_posted_and_the_transcript_returned():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=TRANSCRIPT)

    async with _client(handler) as http:
        # The trailing slash is what a hand-typed NARRATOR_URL often carries.
        assert await transcribe(http, "http://narrator:8000/", b"IMG", "rtl") == TRANSCRIPT

    [request] = seen
    assert request.method == "POST"
    assert request.url.path == "/v1/pages"
    assert request.url.params["direction"] == "rtl"
    assert request.content == b"IMG"


async def test_an_error_answer_is_a_failure_that_carries_the_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "the body is not an image that decodes"})

    async with _client(handler) as http:
        with pytest.raises(NarratorFailed, match="not an image"):
            await transcribe(http, "http://narrator:8000", b"IMG", "ltr")


async def test_an_error_answer_with_no_detail_still_names_the_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async with _client(handler) as http:
        with pytest.raises(NarratorFailed, match="500"):
            await transcribe(http, "http://narrator:8000", b"IMG", "ltr")


async def test_an_unreachable_narrator_is_a_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _client(handler) as http:
        with pytest.raises(NarratorFailed):
            await transcribe(http, "http://narrator:8000", b"IMG", "ltr")


async def test_a_timeout_is_a_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with _client(handler) as http:
        with pytest.raises(NarratorFailed):
            await transcribe(http, "http://narrator:8000", b"IMG", "ltr")


async def test_an_answer_that_is_not_a_transcript_is_a_failure():
    answers = iter(
        [
            httpx.Response(200, json={"unexpected": True}),
            httpx.Response(200, text="<html>not json</html>"),
            httpx.Response(200, json={"panels": "nope"}),
            httpx.Response(200, json=["a", "list"]),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(answers)

    async with _client(handler) as http:
        for _ in range(4):
            with pytest.raises(NarratorFailed):
                await transcribe(http, "http://narrator:8000", b"IMG", "ltr")
