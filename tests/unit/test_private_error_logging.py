import json

import httpx
import pytest
import structlog
from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError
from structlog.testing import capture_logs

from app.core.errors import install_error_handlers


@pytest.mark.asyncio
@pytest.mark.parametrize("database_error", [False, True])
async def test_unhandled_errors_never_log_private_payloads(database_error, monkeypatch):
    app = FastAPI()
    install_error_handlers(app)
    secret = "PRIVATE_DOCUMENT_9b1f password=hidden"

    @app.get("/fail")
    async def fail():
        if database_error:
            raise IntegrityError(
                "INSERT INTO queries VALUES (:question)", {"question": secret}, ValueError(secret)
            )
        raise ValueError(secret)

    with capture_logs() as logs:
        # Earlier app factories can leave this module's cached logger bound to an
        # older processor list. A fresh real logger uses this capture's processors.
        monkeypatch.setattr("app.core.errors.log", structlog.get_logger("docqa.errors"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/fail")
    assert response.status_code == (409 if database_error else 500)
    assert secret not in response.text
    assert secret not in json.dumps(logs, default=str)
    assert any(row.get("error_type") == "ValueError" for row in logs)
    assert all(not row.get("exc_info") for row in logs)
