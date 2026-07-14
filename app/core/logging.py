"""structlog JSON logging and the request-id middleware.

Every request gets a request_id (incoming ``X-Request-Id`` when well-formed, otherwise
a generated uuid). It is bound to a contextvar so every log line and every problem+json
error carries it, echoed back in the response headers, and one summary line is logged
per request. uvicorn's own access log is disabled — it would duplicate that line.
"""

import logging
import re
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")

_shared_processors: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.format_exc_info,
]


def configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            *_shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True


def get_request_id() -> str | None:
    rid = structlog.contextvars.get_contextvars().get("request_id")
    return rid if isinstance(rid, str) else None


class RequestContextMiddleware:
    """Pure ASGI middleware: request_id contextvar + response header + access log line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._log = structlog.get_logger("docqa.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming: str | None = None
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if incoming and REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self._log.info(
                "request",
                method=scope["method"],
                path=scope["path"],
                status=status_code,
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
