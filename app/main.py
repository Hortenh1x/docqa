"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.v1 import collections, documents, health, query, usage
from app.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.redis import close_redis
from app.db.base import dispose_engine

_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes (no auth)."},
    {"name": "collections", "description": "Document groups; each pins an embedding model."},
    {"name": "documents", "description": "Upload, status tracking and deletion."},
    {
        "name": "query",
        "description": "Grounded answers with page-level citations — or an honest refusal.",
    },
    {"name": "usage", "description": "Tenant usage aggregates (tokens, cost, refusal rate)."},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_redis()
    await dispose_engine()


def _install_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=_TAGS,
        )
        schema.setdefault("components", {})["securitySchemes"] = {
            "bearerApiKey": {
                "type": "http",
                "scheme": "bearer",
                "description": "API key: `Authorization: Bearer dqa_live_…`",
            },
            "headerApiKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Same key for clients that prefer a plain header.",
            },
        }
        schema["security"] = [{"bearerApiKey": []}, {"headerApiKey": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app() -> FastAPI:
    settings = get_settings()  # fail fast on missing configuration
    configure_logging(settings.log_level)

    app = FastAPI(
        title="DocQA",
        version="0.3.0",
        description=(
            "Multi-tenant document Q&A API: upload documents, ask questions, get answers "
            "with page-level citations — or an honest 'not found'."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-Id",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "Retry-After",
            "X-Idempotency-Replay",
        ],
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(collections.router)
    app.include_router(documents.router)
    app.include_router(query.router)
    app.include_router(usage.router)
    _install_openapi(app)
    return app


app = create_app()
