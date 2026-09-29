"""Run one extraction inside the worker, and the small helpers the API shares with it."""

import asyncio
import concurrent.futures
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.billing.context import BillingActor
from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.billing.jobs import attributed
from app.config import get_settings
from app.db.models import (
    Chunk,
    Collection,
    Document,
    Extraction,
    ExtractionSchema,
    ExtractionStatus,
    Tenant,
    User,
)
from app.db.sync import sync_session
from app.embeddings import get_embedding_provider
from app.embeddings.base import EmbeddingError
from app.extraction.context import FACTS_SECTION, load_chunks, render_context, select_chunks
from app.extraction.evidence import find_evidence
from app.extraction.fields import SchemaDefinition, parse_definition, response_schema
from app.extraction.prompts import SYSTEM, user_prompt
from app.extraction.validate import validate
from app.generation.llm import GenerationError, get_llm_provider
from app.ingestion.access import FAIL_CLOSED_LABEL, LABEL_ALL
from app.ingestion.chunking import TokenCounter
from app.usage.costs import cost_usd

log = structlog.get_logger("docqa.extraction")


def _run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _billing(session: Any, extraction: Extraction) -> tuple[BillingActor | None, bool]:
    """Same contract as collection_billing: personal tenants pay through the ledger with
    the identity saved on the row, service tenants are operator-paid."""
    if not get_settings().budget_enabled:
        return None, False
    kind = session.scalar(select(Tenant.kind).where(Tenant.id == extraction.tenant_id))
    if kind == "service":
        return None, True
    if extraction.billing_user_id is None or not extraction.billing_ip_digest:
        raise BudgetUnavailableError("Extraction has no saved billing identity.")
    user = session.get(User, extraction.billing_user_id)
    if user is None or not user.is_active:
        raise BudgetUnavailableError("Extraction owner is unavailable.")
    return BillingActor(extraction.billing_ip_digest, user.id), False


def facts_text(schema_name: str, definition: SchemaDefinition, fields: dict[str, Any]) -> str:
    parts = []
    for spec in definition.fields:
        value = (fields.get(spec.name) or {}).get("value")
        if value is None:
            continue
        rendered = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        parts.append(f"{spec.label}: {rendered}")
    return f"{FACTS_SECTION} ({schema_name})\n\n" + "\n".join(parts) if parts else ""


def _facts_label(labels: set[str]) -> str:
    """The facts chunk may summarise restricted sections: label it with the document's
    single restricted label, or fail closed when there are several."""
    restricted = {label for label in labels if label != LABEL_ALL}
    if not restricted:
        return LABEL_ALL
    if len(restricted) == 1:
        return restricted.pop()
    return FAIL_CLOSED_LABEL


def run_extraction(extraction_id: uuid.UUID) -> None:
    settings = get_settings()
    token = uuid.uuid4()
    with sync_session() as session:
        extraction = session.get(Extraction, extraction_id, with_for_update=True)
        if extraction is None or extraction.status in (
            ExtractionStatus.READY,
            ExtractionStatus.FAILED,
        ):
            return
        if extraction.status == ExtractionStatus.PROCESSING and extraction.processing_token:
            return
        extraction.status = ExtractionStatus.PROCESSING
        extraction.processing_token = token
        extraction.updated_at = datetime.now(UTC)
        schema = session.get(ExtractionSchema, extraction.schema_id)
        document = session.get(Document, extraction.document_id)
        if schema is None or document is None:
            extraction.status = ExtractionStatus.FAILED
            extraction.error = "Schema or document vanished."
            return
        definition = parse_definition(
            schema.fields, schema.rules, max_fields=settings.extraction_max_fields
        )
        schema_name, index_facts = schema.name, schema.index_facts
        chunks = load_chunks(session, document.id)
        embeddings: dict[int, list[float]] = {}
        if sum(c.token_count for c in chunks) > settings.extraction_full_text_tokens:
            rows = session.execute(
                select(Chunk.id, Chunk.embedding).where(Chunk.document_id == document.id)
            ).all()
            embeddings = {int(cid): list(vec) for cid, vec in rows}
        collection_id = document.collection_id
        layout = document.ocr_layout
        previous = dict(extraction.fields or {})
        payer, operator = _billing(session, extraction)

    log_ctx = log.bind(extraction_id=str(extraction_id))
    try:
        selected = _run_async(
            attributed(select_chunks(chunks, embeddings, definition, settings), payer, operator)
        )
        provider = get_llm_provider(settings)
        result = _run_async(
            attributed(
                provider.complete_json(
                    SYSTEM,
                    user_prompt(definition, schema_name, render_context(selected)),
                    response_schema(definition),
                    max_tokens=settings.extraction_max_tokens,
                ),
                payer,
                operator,
            )
        )
    except (BudgetExceededError, BudgetUnavailableError) as exc:
        _fail(extraction_id, token, f"{exc.code}: {exc.detail}")
        return
    except (GenerationError, EmbeddingError) as exc:
        log_ctx.warning("extraction_provider_failed", error_type=type(exc).__name__)
        _fail(extraction_id, token, f"Provider error: {exc}")
        return
    except Exception:
        log_ctx.exception("extraction_unexpected_error")
        _fail(extraction_id, token, "Extraction failed. See worker logs.")
        return

    raw_fields = result.content.get("fields") if isinstance(result.content, dict) else None
    values, quotes, issues = validate(
        definition, raw_fields if isinstance(raw_fields, dict) else {}
    )
    fields: dict[str, Any] = {}
    for spec in definition.fields:
        kept = previous.get(spec.name)
        if isinstance(kept, dict) and kept.get("edited"):
            fields[spec.name] = kept  # a human's correction outlives re-runs
            continue
        value = values.get(spec.name)
        evidence, confidence = find_evidence(value, quotes.get(spec.name), chunks, layout)
        if value is not None and evidence is None:
            issues.append(
                {
                    "field": spec.name,
                    "code": "evidence_not_found",
                    "message": f"{spec.label}: the quoted passage was not found in the document",
                }
            )
        fields[spec.name] = {
            "value": value,
            "confidence": confidence if value is not None else None,
            "evidence": evidence if value is not None else None,
            "edited": False,
        }

    text = facts_text(schema_name, definition, fields) if index_facts else ""
    embedding = None
    if text:
        try:
            [embedding] = _run_async(
                attributed(get_embedding_provider(settings).embed([text]), payer, operator)
            )
        except (BudgetExceededError, BudgetUnavailableError, EmbeddingError) as exc:
            log_ctx.warning("extraction_facts_not_indexed", error_type=type(exc).__name__)
            issues.append(
                {
                    "field": None,
                    "code": "facts_not_indexed",
                    "message": "Facts could not be indexed. Re-run to retry.",
                }
            )

    with sync_session() as session:
        # Document deletion locks Collection before its Extraction FK cascades.
        # Follow that order so finalization cannot deadlock with deletion.
        if session.get(Collection, collection_id, with_for_update=True) is None:
            return
        extraction = session.get(Extraction, extraction_id, with_for_update=True)
        if extraction is None or extraction.processing_token != token:
            return
        extraction.fields = fields
        extraction.issues = issues
        extraction.model = provider.model_name
        extraction.prompt_tokens = result.prompt_tokens
        extraction.completion_tokens = result.completion_tokens
        extraction.cost_usd = cost_usd(
            provider.model_name, result.prompt_tokens, result.completion_tokens
        )
        extraction.status = ExtractionStatus.READY
        extraction.error = None
        extraction.processing_token = None
        extraction.updated_at = datetime.now(UTC)
        tenant_id = extraction.tenant_id
        extraction.facts_chunk_id = _replace_facts(
            session,
            extraction.document_id,
            extraction.facts_chunk_id,
            text if embedding is not None else "",
            embedding,
        )

    log_ctx.info(
        "extraction_done",
        fields=sum(1 for f in fields.values() if f.get("value") is not None),
        issues=len(issues),
        tenant_id=str(tenant_id),
    )


def _fail(extraction_id: uuid.UUID, token: uuid.UUID, error: str) -> None:
    with sync_session() as session:
        extraction = session.get(Extraction, extraction_id, with_for_update=True)
        if extraction is None or extraction.processing_token != token:
            return
        extraction.status = ExtractionStatus.FAILED
        extraction.error = error
        extraction.processing_token = None
        extraction.updated_at = datetime.now(UTC)


def _replace_facts(
    session: Session,
    document_id: uuid.UUID,
    old_chunk_id: int | None,
    text: str,
    embedding: list[float] | None,
) -> int | None:
    """Replace the retrieval passage atomically with the extraction's final result."""
    collection_id = session.scalar(select(Document.collection_id).where(Document.id == document_id))
    if collection_id is None:
        return None
    collection = session.get(Collection, collection_id, with_for_update=True)
    if collection is None:
        return None
    labels = set(
        session.scalars(
            select(Chunk.access_label)
            .where(
                Chunk.document_id == document_id,
                or_(Chunk.section_path.is_(None), Chunk.section_path != FACTS_SECTION),
            )
            .distinct()
        )
    )
    if old_chunk_id is not None:
        session.execute(
            delete(Chunk).where(Chunk.id == old_chunk_id, Chunk.document_id == document_id)
        )
        collection.source_generation += 1
    if not text or embedding is None:
        return None
    next_index = (
        int(
            session.scalar(
                select(func.coalesce(func.max(Chunk.chunk_index), -1)).where(
                    Chunk.document_id == document_id
                )
            )
        )
        + 1
    )
    chunk = Chunk(
        document_id=document_id,
        chunk_index=next_index,
        content=text,
        token_count=TokenCounter().count(text),
        section_path=FACTS_SECTION,
        access_label=_facts_label(labels),
        embedding=embedding,
    )
    session.add(chunk)
    session.flush()
    collection.source_generation += 1
    return int(chunk.id)


def remove_facts_chunk(document_id: uuid.UUID, chunk_id: int | None) -> None:
    if chunk_id is None:
        return
    with sync_session() as session:
        collection_id = session.scalar(
            select(Document.collection_id).where(Document.id == document_id)
        )
        if collection_id is not None:
            collection = session.get(Collection, collection_id, with_for_update=True)
            if collection is not None:
                collection.source_generation += 1
        session.execute(delete(Chunk).where(Chunk.id == chunk_id, Chunk.document_id == document_id))
