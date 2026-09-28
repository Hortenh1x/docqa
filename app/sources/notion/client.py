"""Thin synchronous Notion API client (the sync runs inside a Celery task).

Handles the three things every caller would otherwise get wrong: the version header,
cursor pagination, and the 3 requests/second rate limit (429 + ``Retry-After``).
"""

import re
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import httpx

from app.sources.base import SourceAuthError, SourceError, SourceTransientError

_ID_RE = re.compile(r"[0-9a-f]{32}", re.IGNORECASE)
_MIN_INTERVAL_S = 0.34  # Notion allows ~3 requests per second on average
_MAX_ATTEMPTS = 5
_PAGE_SIZE = 100


def normalize_id(value: str) -> str | None:
    """Notion ids as the API returns them (dashed UUID) from an id or a page URL."""
    candidate = value.strip()
    if "/" in candidate or "?" in candidate:
        path = urlparse(candidate).path
        matches = _ID_RE.findall(path.replace("-", ""))
        if not matches:
            return None
        candidate = matches[-1]
    compact = candidate.replace("-", "").lower()
    if not _ID_RE.fullmatch(compact):
        return None
    return f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:]}"


class NotionClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str,
        api_version: str,
        timeout_s: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": api_version,
                "Content-Type": "application/json",
            },
            timeout=timeout_s,
            transport=transport,
        )
        self._sleep = sleep
        self._last_request_at = 0.0

    def close(self) -> None:
        self._http.close()

    # -- transport -------------------------------------------------------------------

    def _throttle(self) -> None:
        wait = self._last_request_at + _MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            self._sleep(wait)
        self._last_request_at = time.monotonic()

    def request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        delay = 1.0
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            self._throttle()
            try:
                response = self._http.request(method, path, json=json)
            except httpx.HTTPError as exc:
                if attempt == _MAX_ATTEMPTS:
                    raise SourceTransientError(f"Notion unreachable: {type(exc).__name__}") from exc
                self._sleep(delay)
                delay *= 2
                continue
            if response.status_code in (401, 403):
                raise SourceAuthError("Notion rejected the integration token.")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == _MAX_ATTEMPTS:
                    raise SourceTransientError(f"Notion answered {response.status_code}.")
                retry_after = response.headers.get("Retry-After")
                try:
                    pause = float(retry_after) if retry_after else delay
                except ValueError:
                    pause = delay
                self._sleep(min(max(pause, 0.0), 60.0))
                delay *= 2
                continue
            if response.status_code == 404:
                raise NotionNotFound(path)
            if response.status_code >= 400:
                raise SourceError(f"Notion answered {response.status_code} for {method} {path}.")
            try:
                return response.json()
            except ValueError as exc:
                raise SourceTransientError("Notion returned a non-JSON body.") from exc
        raise SourceTransientError("Notion request retries exhausted.")  # pragma: no cover

    def _paginate(self, method: str, path: str, body: dict[str, Any] | None) -> Iterator[Any]:
        cursor: str | None = None
        while True:
            if method == "GET":
                query = f"?page_size={_PAGE_SIZE}" + (f"&start_cursor={cursor}" if cursor else "")
                payload = self.request("GET", path + query)
            else:
                page_body = dict(body or {}, page_size=_PAGE_SIZE)
                if cursor:
                    page_body["start_cursor"] = cursor
                payload = self.request(method, path, page_body)
            if not isinstance(payload, dict):
                raise SourceTransientError("Notion returned an unexpected payload.")
            yield from payload.get("results", [])
            if not payload.get("has_more"):
                return
            cursor = payload.get("next_cursor")
            if not cursor:
                return

    # -- endpoints -------------------------------------------------------------------

    def me(self) -> Any:
        return self.request("GET", "/v1/users/me")

    def search(self, object_type: str) -> Iterator[dict[str, Any]]:
        body = {"filter": {"value": object_type, "property": "object"}}
        yield from self._paginate("POST", "/v1/search", body)

    def block_children(self, block_id: str) -> Iterator[dict[str, Any]]:
        yield from self._paginate("GET", f"/v1/blocks/{block_id}/children", None)

    def block(self, block_id: str) -> dict[str, Any]:
        payload = self.request("GET", f"/v1/blocks/{block_id}")
        return payload if isinstance(payload, dict) else {}

    def page(self, page_id: str) -> dict[str, Any]:
        payload = self.request("GET", f"/v1/pages/{page_id}")
        return payload if isinstance(payload, dict) else {}


class NotionNotFound(SourceError):
    """404 — the object is gone or not shared with the integration."""
