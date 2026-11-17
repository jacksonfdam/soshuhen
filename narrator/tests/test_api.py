import asyncio

import cv2
import httpx
import pytest
from fastapi import FastAPI

from narrator.main import create_app
from tests.test_page import IN_PANEL, grid, lettering


@pytest.fixture
def png() -> bytes:
    encoded, buffer = cv2.imencode(".png", grid())
    assert encoded
    return buffer.tobytes()


class Client:
    """Calls the application in process, with no server and no socket.

    httpx's own ASGI transport rather than Starlette's test client, which now warns that it wants
    a different HTTP library than the one this project pins.
    """

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def _send(self, method: str, url: str, content: bytes | None = None) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport, base_url="http://narrator") as http:
                return await http.request(method, url, content=content)

        return asyncio.run(send())

    def post(self, url: str, content: bytes) -> httpx.Response:
        return self._send("POST", url, content)

    def get(self, url: str) -> httpx.Response:
        return self._send("GET", url)


@pytest.fixture
def client() -> Client:
    return Client(create_app(lettering(*IN_PANEL)))


def test_a_page_comes_back_as_a_transcript(client, png):
    response = client.post("/v1/pages?direction=rtl", content=png)

    assert response.status_code == 200
    body = response.json()
    assert (body["width"], body["height"]) == (1200, 800)
    assert body["panels"][0]["blocks"][0]["text"] == "Top right"


def test_the_direction_asked_for_is_the_direction_read(client, png):
    response = client.post("/v1/pages?direction=ltr", content=png)

    assert response.json()["panels"][0]["blocks"][0]["text"] == "Top left"


def test_direction_is_required_and_checked(client, png):
    assert client.post("/v1/pages", content=png).status_code == 422
    assert client.post("/v1/pages?direction=up", content=png).status_code == 422


def test_bytes_that_are_not_an_image_are_422(client):
    response = client.post("/v1/pages?direction=ltr", content=b"not an image")

    assert response.status_code == 422
    assert "image" in response.json()["detail"]


def test_an_empty_body_is_422(client):
    assert client.post("/v1/pages?direction=ltr", content=b"").status_code == 422


def test_an_image_cut_short_is_422(client, png):
    assert client.post("/v1/pages?direction=ltr", content=png[:200]).status_code == 422


def test_a_body_over_the_limit_is_413(client, png, monkeypatch):
    monkeypatch.setattr("narrator.main.MAX_BODY_BYTES", 10)

    assert client.post("/v1/pages?direction=ltr", content=png).status_code == 413


def test_health(client):
    assert client.get("/healthz").json() == {"ok": True}
