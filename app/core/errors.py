"""Domain errors and their mapping to RFC 9457 problem+json responses.

Policy: a resource belonging to another tenant is answered exactly like a missing one —
404, never 403. A 403 would confirm the resource exists, which is an information leak.
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id

ERROR_TYPE_BASE = "https://docqa.dev/errors/"

log = structlog.get_logger("docqa.errors")


class DomainError(Exception):
    status: int = 500
    code: str = "internal"
    title: str = "Internal error"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extra = extra


class NotFoundError(DomainError):
    status = 404
    code = "not_found"
    title = "Resource not found"


class InvalidApiKeyError(DomainError):
    status = 401
    code = "invalid_api_key"
    title = "Invalid API key"


class TenantInactiveError(DomainError):
    status = 403
    code = "tenant_inactive"
    title = "Tenant is inactive"


class DuplicateDocumentError(DomainError):
    status = 409
    code = "duplicate_document"
    title = "Duplicate document"


class DuplicateCollectionError(DomainError):
    status = 409
    code = "duplicate_collection"
    title = "Duplicate collection"


class PayloadTooLargeError(DomainError):
    status = 413
    code = "payload_too_large"
    title = "Payload too large"


class UnsupportedFileTypeError(DomainError):
    status = 415
    code = "unsupported_file_type"
    title = "Unsupported file type"


class TooManyPagesError(DomainError):
    status = 422
    code = "too_many_pages"
    title = "Too many pages"


class EmbeddingModelMismatchError(DomainError):
    status = 409
    code = "embedding_model_mismatch"
    title = "Embedding model mismatch"


class ProviderUnavailableError(DomainError):
    status = 503
    code = "provider_unavailable"
    title = "Upstream provider unavailable"


def problem_response(
    status: int, code: str, title: str, detail: str, extra: dict[str, Any] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": ERROR_TYPE_BASE + code,
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
    }
    request_id = get_request_id()
    if request_id:
        body["request_id"] = request_id
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


_HTTP_CODES = {
    401: ("unauthorized", "Unauthorized"),
    403: ("forbidden", "Forbidden"),
    404: ("not_found", "Resource not found"),
    405: ("method_not_allowed", "Method not allowed"),
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return problem_response(exc.status, exc.code, exc.title, exc.detail, exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, title = _HTTP_CODES.get(exc.status_code, ("http_error", "HTTP error"))
        return problem_response(exc.status_code, code, title, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"loc": [str(part) for part in e["loc"]], "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return problem_response(
            400,
            "validation_error",
            "Validation error",
            "Request validation failed.",
            {"errors": errors},
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # full traceback stays in the logs (with request_id); the client gets no details
        log.exception("unhandled_error")
        return problem_response(500, "internal", "Internal error", "An internal error occurred.")
