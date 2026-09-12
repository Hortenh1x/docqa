"""Public product configuration; never return credentials or private resource identifiers."""

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter

from app.config import get_settings, is_local_llm_url

router = APIRouter(prefix="/v1", tags=["service"])


@router.get("/site")
async def site_configuration() -> dict[str, Any]:
    settings = get_settings()
    providers = []
    if settings.embedding_provider == "openai":
        providers.append(
            {"name": "OpenAI", "receives": "Document text and questions for search embeddings"}
        )
    if settings.llm_provider == "openai_compat" and not is_local_llm_url(settings.llm_base_url):
        providers.append(
            {
                "name": urlparse(settings.llm_base_url).hostname or "Configured LLM provider",
                "receives": "Questions and selected passages to generate answers and suggestions",
            }
        )
    if settings.rerank_provider == "cohere":
        providers.append(
            {"name": "Cohere", "receives": "Questions and candidate passages for ranking"}
        )
    if settings.google_available:
        providers.append(
            {
                "name": "Google",
                "receives": "Sign-in requests when you choose Google. DocQA receives your "
                "verified email and Google account ID.",
            }
        )
    return {
        "accounts_enabled": settings.accounts_enabled,
        "upload_max_mb": settings.max_upload_bytes // (1024 * 1024),
        "operator_contact": settings.service_operator_contact,
        "providers": providers,
        "purpose": (
            "This service is for exploring document Q&A functionality. Use only documents "
            "you have the right to upload; do not use the service for abusive, unlawful "
            "or exploitative purposes."
        ),
        "document_privacy": (
            "Your personal documents are accessible only through your account. External "
            "providers listed here process the stated data. Deleting a document removes it "
            "from your library; protected backup versions may remain for recovery."
        ),
    }
