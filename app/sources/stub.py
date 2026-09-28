"""In-memory connector for tests: the workspace is a process-global dict keyed by the
credential string, so a test can mutate pages between syncs."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from app.sources.base import RenderedItem, SourceAuthError, SourceItem, SourceItemError


@dataclass
class StubPage:
    title: str
    markdown: str
    version: str = "1"
    url: str | None = None
    broken: bool = False


WORKSPACES: dict[str, dict[str, StubPage]] = {}


class StubConnector:
    def __init__(self, credential: str, config: dict[str, Any]) -> None:
        self.credential = credential
        self.config = config

    def _pages(self) -> dict[str, StubPage]:
        try:
            return WORKSPACES[self.credential]
        except KeyError:
            raise SourceAuthError("unknown stub workspace") from None

    def check(self) -> None:
        self._pages()

    def list_items(self) -> Iterator[SourceItem]:
        roots = set(self.config.get("root_ids") or [])
        for external_id, page in self._pages().items():
            if roots and external_id not in roots:
                continue
            yield SourceItem(
                external_id=external_id, title=page.title, url=page.url, version=page.version
            )

    def render(self, item: SourceItem) -> RenderedItem:
        page = self._pages()[item.external_id]
        if page.broken:
            raise SourceItemError("stub page marked broken")
        return RenderedItem(title=page.title, markdown=page.markdown)
