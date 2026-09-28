"""Notion client + connector against an httpx MockTransport (no network)."""

import json

import httpx
import pytest

from app.sources.base import SourceAuthError, SourceTransientError
from app.sources.notion.client import NotionClient, normalize_id
from app.sources.notion.connector import NotionConnector

DASHED = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
COMPACT = DASHED.replace("-", "")


@pytest.mark.parametrize(
    "raw",
    [
        DASHED,
        COMPACT,
        f"https://www.notion.so/acme/Travel-Policy-{COMPACT}",
        f"https://www.notion.so/acme/{COMPACT}?v=abc",
        f"  {DASHED}  ",
    ],
)
def test_normalize_id_accepts_ids_and_urls(raw):
    assert normalize_id(raw) == DASHED


@pytest.mark.parametrize("raw", ["", "not-an-id", "https://www.notion.so/acme/", "1234"])
def test_normalize_id_rejects_garbage(raw):
    assert normalize_id(raw) is None


def _client(handler, sleeps=None):
    transport = httpx.MockTransport(handler)
    return NotionClient(
        "secret_x",
        base_url="https://api.notion.test",
        api_version="2022-06-28",
        timeout_s=5,
        transport=transport,
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
    )


def test_headers_pagination_and_cursor():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        if body.get("start_cursor") is None:
            return httpx.Response(
                200, json={"results": [1, 2], "has_more": True, "next_cursor": "c2"}
            )
        assert body["start_cursor"] == "c2"
        return httpx.Response(200, json={"results": [3], "has_more": False, "next_cursor": None})

    client = _client(handler)
    assert list(client.search("page")) == [1, 2, 3]
    assert seen[0].headers["Notion-Version"] == "2022-06-28"
    assert seen[0].headers["Authorization"] == "Bearer secret_x"
    assert json.loads(seen[0].content)["filter"] == {"value": "page", "property": "object"}
    assert json.loads(seen[0].content)["page_size"] == 100


def test_get_pagination_uses_query_string():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "start_cursor" not in str(request.url):
            return httpx.Response(
                200, json={"results": ["a"], "has_more": True, "next_cursor": "n"}
            )
        return httpx.Response(200, json={"results": ["b"], "has_more": False})

    assert list(_client(handler).block_children("blk")) == ["a", "b"]
    assert calls[0].endswith("/v1/blocks/blk/children?page_size=100")
    assert calls[1].endswith("/v1/blocks/blk/children?page_size=100&start_cursor=n")


def test_rate_limit_honours_retry_after_then_succeeds():
    attempts = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json={"object": "user"})

    assert _client(handler, sleeps).me() == {"object": "user"}
    assert len(attempts) == 2
    assert 2.0 in sleeps


def test_auth_failure_is_not_retried():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(401, json={"code": "unauthorized"})

    with pytest.raises(SourceAuthError):
        _client(handler).me()
    assert len(attempts) == 1


def test_server_errors_exhaust_into_transient_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    with pytest.raises(SourceTransientError):
        _client(handler).me()


def test_network_errors_exhaust_into_transient_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(SourceTransientError):
        _client(handler).me()


# --- connector: scope filtering over search results ---------------------------------

ROOT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CHILD = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
DB = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ROW = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
OUTSIDE = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
IN_COLUMN = "ffffffff-ffff-4fff-8fff-ffffffffffff"
COLUMN_BLOCK = "12121212-1212-4121-8121-121212121212"
ARCHIVED = "34343434-3434-4343-8343-343434343434"


def _page(page_id, parent, title, edited="2026-09-01T00:00:00.000Z", archived=False):
    return {
        "object": "page",
        "id": page_id,
        "archived": archived,
        "last_edited_time": edited,
        "url": f"https://notion.so/{page_id.replace('-', '')}",
        "parent": parent,
        "properties": {
            "title": {"type": "title", "title": [{"type": "text", "plain_text": title}]}
        },
    }


def _workspace_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v1/search":
        kind = json.loads(request.content)["filter"]["value"]
        if kind == "page":
            results = [
                _page(ROOT, {"type": "workspace", "workspace": True}, "Root"),
                _page(CHILD, {"type": "page_id", "page_id": ROOT}, "Child"),
                _page(ROW, {"type": "database_id", "database_id": DB}, "Row"),
                _page(OUTSIDE, {"type": "workspace", "workspace": True}, "Outside"),
                _page(IN_COLUMN, {"type": "block_id", "block_id": COLUMN_BLOCK}, "In column"),
                _page(ARCHIVED, {"type": "page_id", "page_id": ROOT}, "Gone", archived=True),
            ]
        else:
            results = [
                {
                    "object": "database",
                    "id": DB,
                    "last_edited_time": "x",
                    "parent": {"type": "page_id", "page_id": CHILD},
                    "title": [{"type": "text", "plain_text": "Offices"}],
                }
            ]
        return httpx.Response(200, json={"results": results, "has_more": False})
    if path == f"/v1/blocks/{COLUMN_BLOCK}":
        return httpx.Response(
            200,
            json={
                "object": "block",
                "id": COLUMN_BLOCK,
                "parent": {"type": "page_id", "page_id": CHILD},
            },
        )
    if path == f"/v1/blocks/{CHILD}/children":
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "object": "block",
                        "id": "b1",
                        "type": "paragraph",
                        "has_children": False,
                        "paragraph": {"rich_text": [{"type": "text", "plain_text": "Hello"}]},
                    }
                ],
                "has_more": False,
            },
        )
    return httpx.Response(404, json={})


def test_connector_keeps_pages_under_the_root_including_database_rows_and_nested_blocks():
    connector = NotionConnector(
        _client(_workspace_handler), [f"https://notion.so/x/Root-{ROOT.replace('-', '')}"]
    )
    items = {item.external_id: item for item in connector.list_items()}
    assert set(items) == {ROOT, CHILD, ROW, IN_COLUMN}
    assert items[CHILD].title == "Child"
    assert items[CHILD].version == "2026-09-01T00:00:00.000Z"
    assert items[CHILD].url == f"https://notion.so/{CHILD.replace('-', '')}"

    rendered = connector.render(items[CHILD])
    assert rendered.title == "Child"
    assert rendered.markdown == "# Child\n\nHello\n"


def test_connector_without_roots_takes_everything_shared():
    connector = NotionConnector(_client(_workspace_handler), [])
    ids = {item.external_id for item in connector.list_items()}
    assert ids == {ROOT, CHILD, ROW, OUTSIDE, IN_COLUMN}  # archived page excluded
