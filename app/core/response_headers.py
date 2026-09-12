"""Prevent shared/browser HTTP caches from retaining tenant-specific API responses."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class PrivateResponseHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/v1/"):
            await self.app(scope, receive, send)
            return

        async def private_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"x-content-type-options"}
                ]
                message["headers"] = headers + [
                    (b"cache-control", b"private, no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        await self.app(scope, receive, private_send)
