"""OCR preserves durable billing attribution, including eager worker threads."""

import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.billing.context import BillingActor, current_billing_actor, operator_billing
from app.ingestion.ocr.vision import _run_async


@pytest.mark.parametrize(
    "budget,operator,base_url,blocked",
    [
        (True, False, "https://vision.test/v1", True),
        (True, True, "https://vision.test/v1", False),
        (False, False, "https://vision.test/v1", False),
        (True, False, "http://localhost:11435/v1", False),
    ],
)
async def test_hosted_vision_requires_reliable_image_reservation(
    monkeypatch, budget, operator, base_url, blocked
):
    from app.billing.errors import BudgetUnavailableError
    from app.config import get_settings
    from app.ingestion.ocr import vision

    monkeypatch.setattr(get_settings(), "budget_enabled", budget)
    reserve = AsyncMock(return_value=None)
    monkeypatch.setattr(vision, "before_call", reserve)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Page"}}]})

    provider = vision.VisionOcr(base_url, None, "gpt-4o-mini", 10, httpx.MockTransport(respond))
    token = operator_billing.set(operator)
    try:
        if blocked:
            with pytest.raises(BudgetUnavailableError, match="image-token"):
                await provider._transcribe("image")
            assert requests == []
            reserve.assert_not_awaited()
        else:
            assert await provider._transcribe("image") == "Page"
            assert len(requests) == 1
    finally:
        operator_billing.reset(token)


@pytest.mark.parametrize("operator", [False, True])
async def test_vision_thread_preserves_billing_context(operator):
    actor = BillingActor("saved-upload", uuid.uuid4())
    actor_token = current_billing_actor.set(actor)
    operator_token = operator_billing.set(operator)
    try:

        async def read_context():
            return current_billing_actor.get(), operator_billing.get()

        assert _run_async(read_context()) == (actor, operator)
    finally:
        current_billing_actor.reset(actor_token)
        operator_billing.reset(operator_token)


def test_ingestion_parser_uses_saved_billing_identity(monkeypatch, tmp_path):
    from app.db.models import DocumentStatus
    from app.ingestion import tasks
    from app.ingestion.parsers import ParsedDocument

    saved = BillingActor("saved-upload", uuid.uuid4())
    ambient = BillingActor("unrelated-request", uuid.uuid4())
    document = SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        status=DocumentStatus.PENDING,
        next_attempt_at=None,
        ingestion_attempts=0,
        sha256="hash",
        mime_type="text/plain",
    )
    session = Mock()
    session.execute.return_value.first.return_value = document, uuid.uuid4()

    @contextmanager
    def sync_session():
        yield session

    observed = []

    def parse(path):
        observed.append((current_billing_actor.get(), operator_billing.get()))
        return ParsedDocument(pages=[])

    async def embed(texts):
        return []

    monkeypatch.setattr(tasks, "sync_session", sync_session)
    monkeypatch.setattr(tasks, "collection_billing", lambda *args: (saved, False))
    monkeypatch.setattr(tasks, "get_storage", lambda: SimpleNamespace(path_for=lambda *a: tmp_path))
    monkeypatch.setattr(tasks, "get_parser", lambda _: SimpleNamespace(parse=parse))
    monkeypatch.setattr(tasks, "get_embedding_provider", lambda _: SimpleNamespace(embed=embed))
    monkeypatch.setattr(tasks, "_write_searchable_pdf", lambda *a: None)
    monkeypatch.setattr(tasks, "_store_chunks", lambda *a, **kw: True)
    monkeypatch.setattr(tasks, "_refresh_suggestions_if_settled", lambda *a, **kw: None)
    actor_token = current_billing_actor.set(ambient)
    operator_token = operator_billing.set(True)
    try:
        tasks.ingest_document.run(str(document.id))
        assert observed == [(saved, False)]
        assert current_billing_actor.get() == ambient
        assert operator_billing.get() is True
    finally:
        current_billing_actor.reset(actor_token)
        operator_billing.reset(operator_token)
