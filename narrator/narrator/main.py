"""The service: a page image in, a transcript out. No state, no storage, no outbound calls."""

import asyncio
from typing import Any, Literal

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request

from narrator.lines import LineEngine
from narrator.page import as_json, read_page

# Far above any page a source serves; the longest strip seen in a real library was under 3 MB.
# The limit is here so a mistaken or hostile caller cannot make this process hold a gigabyte.
MAX_BODY_BYTES = 40 * 1024 * 1024


def create_app(engine: LineEngine | None = None) -> FastAPI:
    """The application. Tests pass a stand-in engine; the service loads the real one on first use."""
    app = FastAPI(title="Soshuhen narrator", docs_url=None, redoc_url=None, openapi_url=None)
    held: dict[str, LineEngine] = {} if engine is None else {"engine": engine}
    # Recognition is CPU-bound and already uses every core. Two pages at once only make both
    # slower, so they take turns.
    turn = asyncio.Lock()

    def loaded() -> LineEngine:
        if "engine" not in held:
            from narrator.engine import RapidOcrEngine

            held["engine"] = RapidOcrEngine()
        return held["engine"]

    @app.get("/healthz")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/pages")
    async def page(
        request: Request, direction: Literal["rtl", "ltr"] = Query(...)
    ) -> dict[str, Any]:
        image = _decode(await _body(request))
        async with turn:
            # Off the event loop, so a page being read does not hold up the health check.
            transcript = await asyncio.to_thread(
                read_page, image, loaded(), right_to_left=direction == "rtl"
            )
        return as_json(transcript)

    return app


async def _body(request: Request) -> bytes:
    """The request body, refused as soon as it is known to be over the limit."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="the page is larger than this service accepts")
    received = bytearray()
    # Counted as it arrives: a body sent in chunks declares no length to check beforehand.
    async for chunk in request.stream():
        received += chunk
        if len(received) > MAX_BODY_BYTES:
            raise HTTPException(
                status_code=413, detail="the page is larger than this service accepts"
            )
    return bytes(received)


def _decode(data: bytes) -> np.ndarray:
    image = None
    if data:
        # imdecode answers None for bytes it cannot read, and raises for none at all.
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise HTTPException(status_code=422, detail="the body is not an image that decodes")
    return image


app = create_app()
