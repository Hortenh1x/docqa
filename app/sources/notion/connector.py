"""Listing and rendering of a Notion workspace.

Listing uses ``POST /v1/search`` (every page and database the integration was shared
with, each with ``last_edited_time`` and its parent) and keeps the pages whose ancestor
chain reaches one of the configured roots — or everything when no root is configured.
Only pages become documents; databases are scope nodes whose rows are pages.
"""

from collections.abc import Iterator
from typing import Any

import httpx

from app.config import get_settings
from app.sources.base import RenderedItem, SourceItem, SourceItemError, SourceTransientError
from app.sources.notion.client import NotionClient, NotionNotFound, normalize_id
from app.sources.notion.render import MarkdownRenderer, page_title


class NotionConnector:
    def __init__(self, client: NotionClient, root_ids: list[str]) -> None:
        self._client = client
        self._roots = {r for r in (normalize_id(x) for x in root_ids) if r}
        self._pages: dict[str, dict[str, Any]] = {}
        # parent page/database id per block id — pages nested in columns/toggles
        self._block_parent_cache: dict[str, tuple[str, str] | None] = {}

    @classmethod
    def from_config(
        cls,
        token: str,
        config: dict[str, Any],
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> "NotionConnector":
        settings = get_settings()
        client = NotionClient(
            token,
            base_url=settings.notion_base_url,
            api_version=settings.notion_api_version,
            timeout_s=settings.notion_timeout_s,
            transport=transport,
        )
        return cls(client, list(config.get("root_ids") or []))

    def close(self) -> None:
        self._client.close()

    def check(self) -> None:
        self._client.me()

    # -- listing ---------------------------------------------------------------------

    def list_items(self) -> Iterator[SourceItem]:
        objects: dict[str, dict[str, Any]] = {}
        for object_type in ("page", "database"):
            for obj in self._client.search(object_type):
                if obj.get("archived") or obj.get("in_trash"):
                    continue
                object_id = normalize_id(str(obj.get("id") or ""))
                if object_id:
                    objects[object_id] = obj
        self._pages = {k: v for k, v in objects.items() if v.get("object") == "page"}
        in_scope_cache: dict[str, bool] = {}
        for page_id, page in self._pages.items():
            if not self._in_scope(page_id, objects, in_scope_cache, hops=0):
                continue
            yield SourceItem(
                external_id=page_id,
                title=page_title(page),
                url=str(page.get("url") or "") or None,
                version=str(page.get("last_edited_time") or ""),
            )

    def _parent_ref(self, obj: dict[str, Any]) -> tuple[str, str] | None:
        parent = obj.get("parent") or {}
        kind = parent.get("type")
        if kind in ("page_id", "database_id"):
            parent_id = normalize_id(str(parent.get(kind) or ""))
            return (kind, parent_id) if parent_id else None
        if kind == "block_id":
            block_id = normalize_id(str(parent.get("block_id") or ""))
            return self._block_parent(block_id) if block_id else None
        return None  # workspace-level

    def _block_parent(self, block_id: str) -> tuple[str, str] | None:
        if block_id in self._block_parent_cache:
            return self._block_parent_cache[block_id]
        try:
            block = self._client.block(block_id)
        except NotionNotFound:
            block = {}
        ref = self._parent_ref(block) if block else None
        self._block_parent_cache[block_id] = ref
        return ref

    def _in_scope(
        self,
        object_id: str,
        objects: dict[str, dict[str, Any]],
        cache: dict[str, bool],
        hops: int,
    ) -> bool:
        if not self._roots:
            return True
        if object_id in cache:
            return cache[object_id]
        if object_id in self._roots:
            cache[object_id] = True
            return True
        if hops > 64:
            return False
        obj = objects.get(object_id)
        if obj is None:
            cache[object_id] = False
            return False
        ref = self._parent_ref(obj)
        result = False
        if ref is not None:
            _, parent_id = ref
            result = parent_id in self._roots or self._in_scope(parent_id, objects, cache, hops + 1)
        cache[object_id] = result
        return result

    # -- rendering -------------------------------------------------------------------

    def render(self, item: SourceItem) -> RenderedItem:
        page = self._pages.get(item.external_id)
        try:
            if page is None:
                page = self._client.page(item.external_id)
            blocks = list(self._client.block_children(item.external_id))
        except NotionNotFound as exc:
            raise SourceItemError("page is no longer accessible") from exc
        renderer = MarkdownRenderer(self._children)
        try:
            markdown = renderer.render_page(page, blocks)
        except NotionNotFound as exc:
            raise SourceItemError("a nested block is no longer accessible") from exc
        return RenderedItem(title=page_title(page), markdown=markdown)

    def _children(self, block_id: str) -> Iterator[dict[str, Any]]:
        try:
            yield from self._client.block_children(block_id)
        except NotionNotFound:
            return
        except SourceTransientError:
            raise
