"""Schema-driven field extraction: schemas CRUD, per-document extractions, export."""

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.accounts.actor import Actor
from app.api.deps import CurrentCollection, CurrentTenant, DbSession, require_write_access
from app.billing.context import current_billing_actor
from app.config import get_settings
from app.core.errors import (
    DocumentNotReadyError,
    DuplicateSchemaError,
    ExtractionInProgressError,
    ExtractionQuotaExceededError,
    InvalidSchemaError,
    NotFoundError,
)
from app.core.rate_limit import consume_daily, rate_limit
from app.db.models import (
    Collection,
    Document,
    DocumentStatus,
    Extraction,
    ExtractionSchema,
    ExtractionStatus,
)
from app.extraction.fields import FieldSpec, parse_definition
from app.extraction.service import remove_facts_chunk
from app.extraction.tasks import enqueue_extraction
from app.extraction.templates import TEMPLATES

router = APIRouter(prefix="/v1", tags=["extraction"], dependencies=[Depends(rate_limit("default"))])


# --- schemas -----------------------------------------------------------------------------


class SchemaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    fields: list[FieldSpec] = Field(min_length=1)
    rules: list[str] = Field(default_factory=list, max_length=20)
    index_facts: bool = False


class SchemaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    fields: list[FieldSpec] | None = Field(default=None, min_length=1)
    rules: list[str] | None = Field(default=None, max_length=20)
    index_facts: bool | None = None


class SchemaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    fields: list[dict[str, Any]]
    rules: list[str]
    index_facts: bool
    extraction_count: int = 0
    created_at: datetime
    updated_at: datetime


class SchemaTemplateOut(BaseModel):
    key: str
    name: str
    description: str
    fields: list[dict[str, Any]]
    rules: list[str]


def _validated(fields: list[FieldSpec], rules: list[str]) -> list[dict[str, Any]]:
    definition = parse_definition(
        [f.model_dump() for f in fields], rules, max_fields=get_settings().extraction_max_fields
    )
    return [f.model_dump() for f in definition.fields]


async def _schema_counts(db: DbSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(Extraction.schema_id, func.count())
            .where(Extraction.schema_id.in_(ids))
            .group_by(Extraction.schema_id)
        )
    ).all()
    return {schema_id: int(n) for schema_id, n in rows}


async def _fetch_schema(
    db: DbSession, tenant_id: uuid.UUID, schema_id: uuid.UUID
) -> ExtractionSchema:
    schema = await db.scalar(
        select(ExtractionSchema).where(
            ExtractionSchema.id == schema_id, ExtractionSchema.tenant_id == tenant_id
        )
    )
    if schema is None:
        raise NotFoundError("Schema not found.")
    return schema


@router.get("/schemas/templates", response_model=list[SchemaTemplateOut])
async def schema_templates(tenant: CurrentTenant) -> list[SchemaTemplateOut]:
    return [SchemaTemplateOut(**template) for template in TEMPLATES]


@router.post("/schemas", status_code=201, response_model=SchemaOut)
async def create_schema(
    payload: SchemaCreate, tenant: CurrentTenant, db: DbSession, request: Request
) -> SchemaOut:
    require_write_access(request)
    fields = _validated(payload.fields, payload.rules)
    schema = ExtractionSchema(
        tenant_id=tenant.id,
        name=payload.name,
        description=payload.description,
        fields=fields,
        rules=payload.rules,
        index_facts=payload.index_facts,
    )
    db.add(schema)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateSchemaError(f"A schema named '{payload.name}' already exists.") from None
    await db.refresh(schema)
    return SchemaOut.model_validate(schema)


@router.get("/schemas", response_model=list[SchemaOut])
async def list_schemas(tenant: CurrentTenant, db: DbSession) -> list[SchemaOut]:
    schemas = list(
        (
            await db.scalars(
                select(ExtractionSchema)
                .where(ExtractionSchema.tenant_id == tenant.id)
                .order_by(ExtractionSchema.created_at)
            )
        ).all()
    )
    counts = await _schema_counts(db, [s.id for s in schemas])
    return [
        SchemaOut.model_validate(s).model_copy(update={"extraction_count": counts.get(s.id, 0)})
        for s in schemas
    ]


@router.get("/schemas/{schema_id}", response_model=SchemaOut)
async def get_schema(schema_id: uuid.UUID, tenant: CurrentTenant, db: DbSession) -> SchemaOut:
    schema = await _fetch_schema(db, tenant.id, schema_id)
    counts = await _schema_counts(db, [schema.id])
    return SchemaOut.model_validate(schema).model_copy(
        update={"extraction_count": counts.get(schema.id, 0)}
    )


@router.patch("/schemas/{schema_id}", response_model=SchemaOut)
async def update_schema(
    schema_id: uuid.UUID,
    payload: SchemaUpdate,
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
) -> SchemaOut:
    require_write_access(request)
    schema = await _fetch_schema(db, tenant.id, schema_id)
    fields = (
        payload.fields if payload.fields is not None else [FieldSpec(**f) for f in schema.fields]
    )
    rules = payload.rules if payload.rules is not None else list(schema.rules)
    schema.fields = _validated(fields, rules)
    schema.rules = rules
    if payload.name is not None:
        schema.name = payload.name
    if payload.description is not None:
        schema.description = payload.description
    if payload.index_facts is not None:
        schema.index_facts = payload.index_facts
    schema.updated_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateSchemaError(f"A schema named '{payload.name}' already exists.") from None
    await db.refresh(schema)
    counts = await _schema_counts(db, [schema.id])
    return SchemaOut.model_validate(schema).model_copy(
        update={"extraction_count": counts.get(schema.id, 0)}
    )


@router.delete("/schemas/{schema_id}", status_code=204, response_class=Response)
async def delete_schema(
    schema_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> None:
    require_write_access(request)
    schema = await _fetch_schema(db, tenant.id, schema_id)
    facts = (
        await db.execute(
            select(Extraction.document_id, Extraction.facts_chunk_id).where(
                Extraction.schema_id == schema.id, Extraction.facts_chunk_id.isnot(None)
            )
        )
    ).all()
    await db.delete(schema)  # extractions cascade
    await db.commit()
    for document_id, chunk_id in facts:
        remove_facts_chunk(document_id, chunk_id)


# --- extractions ---------------------------------------------------------------------------


class ExtractionRequest(BaseModel):
    schema_id: uuid.UUID
    # re-run: discard human edits too
    force: bool = False


class ExtractionPatch(BaseModel):
    # {name: value} — sets the value and marks the field as edited by a human
    values: dict[str, Any] = Field(default_factory=dict)
    # field names whose value is removed (kept in the schema, cleared here)
    clear: list[str] = Field(default_factory=list)


class ExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    schema_id: uuid.UUID
    status: str
    model: str | None
    fields: dict[str, Any]
    issues: list[dict[str, Any]]
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: Decimal | None
    error: str | None
    created_at: datetime
    updated_at: datetime


async def _owned_document(db: DbSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = await db.scalar(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(Document.id == document_id, Collection.tenant_id == tenant_id)
    )
    if document is None:
        raise NotFoundError("Document not found.")
    return document


async def _fetch_extraction(
    db: DbSession, tenant_id: uuid.UUID, extraction_id: uuid.UUID
) -> Extraction:
    extraction = await db.scalar(
        select(Extraction).where(Extraction.id == extraction_id, Extraction.tenant_id == tenant_id)
    )
    if extraction is None:
        raise NotFoundError("Extraction not found.")
    return extraction


def _quota_scope(request: Request, actor: Actor) -> str:
    if actor.kind == "account" and actor.user_id:
        return f"extract:user:{actor.user_id}"
    prefix = getattr(request.state, "api_key_prefix", None)
    client = request.client.host if request.client else "local"
    return f"extract:{prefix or 'guest'}:{client}"


@router.post(
    "/documents/{document_id}/extractions",
    status_code=202,
    response_model=ExtractionOut,
    responses={
        409: {"description": "Document not ready, or an extraction is still running"},
        429: {"description": "Demo: daily extraction quota exhausted"},
    },
)
async def request_extraction(
    document_id: uuid.UUID,
    payload: ExtractionRequest,
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
) -> ExtractionOut:
    settings = get_settings()
    document = await _owned_document(db, tenant.id, document_id)
    collection = await db.scalar(select(Collection).where(Collection.id == document.collection_id))
    require_write_access(request, collection)
    if document.status != DocumentStatus.READY:
        raise DocumentNotReadyError("Fields can be extracted once the document is ready.")
    schema = await _fetch_schema(db, tenant.id, payload.schema_id)
    actor: Actor = request.state.actor
    if settings.demo_mode:
        quota = await consume_daily(
            _quota_scope(request, actor), settings.demo_max_extractions_per_day
        )
        if not quota.allowed:
            raise ExtractionQuotaExceededError(
                f"The demo allows {quota.limit} extractions per day.",
                headers={"Retry-After": str(quota.retry_after_s)},
            )
    payer = current_billing_actor.get()
    extraction = await db.scalar(
        select(Extraction)
        .where(Extraction.document_id == document.id, Extraction.schema_id == schema.id)
        .with_for_update()
    )
    if extraction is None:
        extraction = Extraction(
            tenant_id=tenant.id,
            document_id=document.id,
            schema_id=schema.id,
            status=ExtractionStatus.PENDING,
            billing_user_id=actor.user_id if actor.kind == "account" else None,
            billing_ip_digest=payer.ip_digest if payer else None,
        )
        db.add(extraction)
    else:
        if extraction.status == ExtractionStatus.PROCESSING and extraction.processing_token:
            raise ExtractionInProgressError("This extraction is still running.")
        if payload.force:
            extraction.fields = {}
        extraction.status = ExtractionStatus.PENDING
        extraction.error = None
        extraction.issues = []
        extraction.processing_token = None
        extraction.updated_at = datetime.now(UTC)
        extraction.billing_user_id = actor.user_id if actor.kind == "account" else None
        extraction.billing_ip_digest = payer.ip_digest if payer else None
    await db.commit()
    await db.refresh(extraction)
    enqueue_extraction(extraction.id)
    await db.refresh(extraction)
    return ExtractionOut.model_validate(extraction)


@router.get("/documents/{document_id}/extractions", response_model=list[ExtractionOut])
async def list_document_extractions(
    document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession
) -> list[ExtractionOut]:
    document = await _owned_document(db, tenant.id, document_id)
    rows = await db.scalars(
        select(Extraction)
        .where(Extraction.document_id == document.id)
        .order_by(Extraction.created_at)
    )
    return [ExtractionOut.model_validate(e) for e in rows]


@router.get("/extractions/{extraction_id}", response_model=ExtractionOut)
async def get_extraction(
    extraction_id: uuid.UUID, tenant: CurrentTenant, db: DbSession
) -> ExtractionOut:
    return ExtractionOut.model_validate(await _fetch_extraction(db, tenant.id, extraction_id))


@router.patch("/extractions/{extraction_id}", response_model=ExtractionOut)
async def patch_extraction(
    extraction_id: uuid.UUID,
    payload: ExtractionPatch,
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
) -> ExtractionOut:
    require_write_access(request)
    extraction = await _fetch_extraction(db, tenant.id, extraction_id)
    schema = await _fetch_schema(db, tenant.id, extraction.schema_id)
    known = {f["name"] for f in schema.fields}
    unknown = [name for name in [*payload.values, *payload.clear] if name not in known]
    if unknown:
        raise InvalidSchemaError(f"unknown fields: {', '.join(sorted(unknown))}")
    fields = dict(extraction.fields or {})
    for name, value in payload.values.items():
        entry = dict(fields.get(name) or {})
        entry.update({"value": value, "confidence": 1.0, "edited": True})
        entry.setdefault("evidence", None)
        fields[name] = entry
    for name in payload.clear:
        fields[name] = {"value": None, "confidence": None, "evidence": None, "edited": True}
    extraction.fields = fields
    extraction.issues = [
        i
        for i in (extraction.issues or [])
        if i.get("field") not in set(payload.values) | set(payload.clear)
    ]
    extraction.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(extraction)
    return ExtractionOut.model_validate(extraction)


@router.delete("/extractions/{extraction_id}", status_code=204, response_class=Response)
async def delete_extraction(
    extraction_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> None:
    require_write_access(request)
    extraction = await _fetch_extraction(db, tenant.id, extraction_id)
    document_id, facts = extraction.document_id, extraction.facts_chunk_id
    await db.delete(extraction)
    await db.commit()
    remove_facts_chunk(document_id, facts)


# --- export ---------------------------------------------------------------------------------


@router.get(
    "/collections/{collection_id}/extractions",
    description=(
        "Every extraction of one schema across the collection — one row per document. "
        "`format=csv` streams a spreadsheet-ready file; JSON otherwise."
    ),
    response_model=None,
)
async def export_extractions(
    collection: CurrentCollection,
    tenant: CurrentTenant,
    db: DbSession,
    schema_id: Annotated[uuid.UUID, Query()],
    format: Annotated[Literal["json", "csv"], Query()] = "json",
) -> Any:
    if collection.tenant_id != tenant.id:
        raise NotFoundError("Collection not found.")
    schema = await _fetch_schema(db, tenant.id, schema_id)
    rows = (
        await db.execute(
            select(Extraction, Document.filename)
            .join(Document, Extraction.document_id == Document.id)
            .where(Document.collection_id == collection.id, Extraction.schema_id == schema.id)
            .order_by(Document.created_at, Document.id)
        )
    ).all()
    names = [f["name"] for f in schema.fields]
    if format == "json":
        return {
            "schema_id": str(schema.id),
            "schema": schema.name,
            "fields": names,
            "rows": [
                {
                    "document_id": str(extraction.document_id),
                    "filename": filename,
                    "status": extraction.status,
                    "values": {n: (extraction.fields or {}).get(n, {}).get("value") for n in names},
                    "issues": len(extraction.issues or []),
                }
                for extraction, filename in rows
            ],
        }

    def _cell(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return "; ".join(str(v) for v in value)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["document_id", "filename", "status", *names, "issues"])
    for extraction, filename in rows:
        values = extraction.fields or {}
        writer.writerow(
            [
                str(extraction.document_id),
                filename,
                extraction.status,
                *[_cell(values.get(n, {}).get("value")) for n in names],
                len(extraction.issues or []),
            ]
        )
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in schema.name) or "schema"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe}.csv"',
            "Cache-Control": "private, no-store",
        },
    )
