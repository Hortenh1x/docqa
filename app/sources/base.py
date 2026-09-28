"""Connector contract.

A connector turns an external workspace into Markdown documents. It is deliberately
split into a cheap listing (ids + version markers, no bodies) and a per-item render, so a
sync only downloads what changed. Every implementation sits behind this Protocol; the
``stub`` connector is an in-memory workspace for tests and the offline demo.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol


class SourceError(Exception):
    """Base for connector failures."""


class SourceAuthError(SourceError):
    """Credentials rejected (401/403) — the source needs new credentials."""


class SourceTransientError(SourceError):
    """Network / 5xx / rate limit after retries — a later sync may succeed."""


class SourceItemError(SourceError):
    """One item could not be rendered; the sync continues with the others."""


@dataclass(frozen=True)
class SourceItem:
    external_id: str
    title: str
    url: str | None
    # opaque change marker (Notion: last_edited_time); equal → nothing to re-render
    version: str


@dataclass(frozen=True)
class RenderedItem:
    title: str
    markdown: str


class SourceConnector(Protocol):
    def check(self) -> None:
        """Validate credentials; raise SourceAuthError / SourceTransientError."""
        ...

    def list_items(self) -> Iterator[SourceItem]:
        """Every item in scope with its current version marker, bodies excluded."""
        ...

    def render(self, item: SourceItem) -> RenderedItem: ...


def get_connector(kind: str, credential: str, config: dict[str, Any]) -> SourceConnector:
    if kind == "notion":
        from app.sources.notion.connector import NotionConnector

        return NotionConnector.from_config(credential, config)
    if kind == "stub":
        from app.sources.stub import StubConnector

        return StubConnector(credential, config)
    raise SourceError(f"unknown source kind {kind!r}")
