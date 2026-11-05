from __future__ import annotations

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipResponder
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_COMPRESSIBLE = ("text/", "application/json", "application/javascript", "application/geo+json", "image/svg+xml")


class _TextResponder(GZipResponder):
    passthrough = False

    async def send_with_gzip(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = Headers(raw=message["headers"])
            self.passthrough = (message["status"] == 206 or "content-range" in headers
                                or not headers.get("content-type", "").startswith(_COMPRESSIBLE))
        if self.passthrough:
            await self.send(message)
        else:
            await super().send_with_gzip(message)


class GZipTextMiddleware:
    """Gzip hanya untuk teks/JSON/JS; raster dan unduhan biner dilewatkan apa adanya."""

    def __init__(self, app: ASGIApp, minimum_size: int = 1024, compresslevel: int = 6) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and "gzip" in Headers(scope=scope).get("accept-encoding", ""):
            responder = _TextResponder(self.app, self.minimum_size, self.compresslevel)
            await responder(scope, receive, send)
        else:
            await self.app(scope, receive, send)
