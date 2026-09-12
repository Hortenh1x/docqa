"""Application settings. Fail fast: missing required variables abort startup."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def is_local_llm_url(base_url: str) -> bool:
    return urlparse(base_url).hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )

    # core — required, no defaults
    database_url: str
    redis_url: str
    # sync DSN for the Celery worker; derived from database_url when unset
    database_url_sync: str | None = None

    # embeddings
    embedding_provider: Literal["stub", "openai", "ollama"] = "stub"
    embedding_dim: int = Field(default=1024, ge=1024, le=1024)  # deployed pgvector dimension
    embed_batch_size: int = Field(default=64, gt=0)
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "bge-m3"

    # chunking
    chunk_target_tokens: int = Field(default=450, gt=0)
    chunk_overlap_tokens: int = Field(default=60, ge=0)
    chunk_max_tokens: int = Field(default=512, gt=0)

    # retrieval (tuned against the eval set in week 4)
    # candidate windows: widened after measuring the recall curve on real corpora
    # (eval/results_retrieval_tuning.md) — a bigger fusion window lifts the right
    # document into the top ranks on collections of near-identical documents
    top_k_vector: int = Field(default=100, gt=0)
    top_k_fts: int = Field(default=100, ge=0)  # zero preserves vector-only eval mode
    rrf_k: int = Field(default=60, gt=0)
    rrf_top_n: int = Field(default=40, gt=0)
    # how many chunks reach the prompt. 8 was the single biggest source of false
    # refusals on long real-world documents: the evidence was retrieved but cut off
    rerank_top_n: int = Field(default=40, gt=0)
    hnsw_ef_search: int = Field(default=200, gt=0)
    # tuned against eval/golden.yaml for the rerank=none cosine gate (see eval/results.md);
    # retune when switching to a real reranker — their score scales differ
    refusal_threshold: float = 0.50

    # reranking
    rerank_provider: Literal["cohere", "local", "none", "stub"] = "none"
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-v3.5"
    rerank_timeout_s: float = Field(default=4.0, gt=0)

    # generation
    llm_provider: Literal["openai_compat", "stub"] = "stub"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_timeout_s: float = Field(default=180.0, gt=0)
    llm_max_tokens: int = Field(default=1024, gt=0)
    # must be large enough for rerank_top_n chunks, or the budget silently
    # re-imposes the old cut (20 chunks x ~450 tokens + headers)
    context_token_budget: int = Field(default=18000, gt=0)
    context_chunk_max_tokens: int = Field(default=700, gt=0)
    # suggested questions: the worker refreshes them when a collection's ingestion
    # settles — count kept, count+2 drafted, ranked by retrieval score
    suggested_questions_enabled: bool = True
    suggested_questions_count: int = Field(default=3, gt=0)

    # rate limiting (token bucket per API key, by endpoint class)
    rate_limit_enabled: bool = True
    rate_limit_query_per_minute: int = Field(default=30, gt=0)
    rate_limit_upload_per_minute: int = Field(default=10, gt=0)
    rate_limit_default_per_minute: int = Field(default=120, gt=0)
    # demo cost cap: fixed-window daily query quota per (api key, client address);
    # 0 disables. Sized against usage/costs.py at the peak-hour rate: a worst-case
    # deepseek-v4-flash query (9k-token context + 4000-char question + 4096-token
    # completion) costs ~$0.010, so 50/day keeps a single visitor under $0.50/day even
    # in the pathological case; a typical query is ~$0.004, i.e. ~$0.20/day.
    rate_limit_query_per_day: int = Field(default=0, ge=0)
    # honor X-Forwarded-For for the client half of the quota scope — enable only
    # behind a proxy that overwrites the header (the deploy Caddy does)
    rate_limit_trust_forwarded_for: bool = False

    # idempotency
    idempotency_ttl_s: int = Field(default=86400, gt=0)

    # access levels: chunks carry a content label (from "Access: … only" markers in the
    # documents); a query carries the caller's role; a role sees the labels listed here.
    # Labels are a partial order on purpose (HR and Finance are siblings, not a ladder).
    # ACCESS_ROLES accepts JSON in the environment. Every role must include "all".
    access_roles: dict[str, list[str]] = {
        "employee": ["all"],
        "manager": ["all", "managers"],
        "hr": ["all", "managers", "hr"],
        "finance": ["all", "managers", "finance"],
        "leadership": ["all", "managers", "hr", "finance", "leadership"],
    }
    # role assumed when a query carries none — least privilege, never "see everything"
    access_default_role: str = "employee"
    # demo mode: tell the client how many relevant passages its role cannot see and which
    # labels would unlock them. This deliberately confirms that restricted content exists
    # (the "403 vs 404" trade-off) — keep it off in deployments where that matters.
    access_reveal_hidden: bool = False

    # public demo mode: read-only demo collections + a small sandbox
    demo_mode: bool = False
    demo_max_files_per_collection: int = Field(default=5, gt=0)
    demo_max_upload_mb: int = Field(default=5, gt=0)

    # CORS (comma-separated origins for the UI; 3002 is the local dev UI port,
    # 3000 covers a locally built ui container with default PORT)
    cors_origins: str = "http://localhost:3000,http://localhost:3002"

    # Browser accounts are opt-in; service API keys remain supported independently.
    accounts_enabled: bool = False
    budget_enabled: bool = False
    budget_daily_usd: Decimal = Field(default=Decimal("0.50"), gt=0, le=Decimal("0.50"))
    budget_ip_secret: str | None = None
    public_tenant_id: UUID | None = None
    auth_allowed_origins: str = "http://localhost:3000,http://localhost:3002"
    auth_public_url: str = "http://localhost:3002"
    auth_session_ttl_s: int = Field(default=604800, ge=300, le=2592000)
    auth_verify_ttl_s: int = Field(default=86400, ge=300, le=172800)
    auth_reset_ttl_s: int = Field(default=1800, ge=300, le=3600)
    auth_attempt_window_s: int = Field(default=900, ge=60)
    auth_attempt_account_limit: int = Field(default=10, ge=1)
    auth_attempt_ip_limit: int = Field(default=50, ge=1)
    google_client_id: str | None = None
    google_client_secret: str | None = Field(default=None, repr=False)
    google_redirect_uri: str = "http://localhost:8000/v1/auth/google/callback"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_s: float = Field(default=10.0, gt=0, le=60)

    # limits
    max_upload_mb: int = Field(default=25, gt=0)
    max_pages: int = Field(default=300, gt=0)

    # misc
    storage_dir: Path = Path("data/files")
    storage_provider: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    s3_region: str = "eu-central-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    log_level: str = "INFO"
    service_operator_contact: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _validate_providers_and_limits(self) -> "Settings":
        if self.storage_provider == "s3":
            if not (self.s3_bucket and self.s3_access_key_id and self.s3_secret_access_key):
                raise ValueError(
                    "S3_BUCKET, S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY are required"
                )
            if self.s3_endpoint_url:
                endpoint = urlparse(self.s3_endpoint_url)
                if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username:
                    raise ValueError("S3_ENDPOINT_URL must be an HTTPS endpoint")
        if self.embedding_provider == "openai" and not (self.openai_api_key or "").strip():
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        if self.rerank_provider == "cohere" and not (self.cohere_api_key or "").strip():
            raise ValueError("COHERE_API_KEY is required when RERANK_PROVIDER=cohere")
        if self.llm_provider == "openai_compat":
            endpoint = urlparse(self.llm_base_url)
            if endpoint.scheme not in ("http", "https") or not endpoint.hostname:
                raise ValueError("LLM_BASE_URL must be an HTTP(S) endpoint")
            if not (self.llm_api_key or "").strip() and not is_local_llm_url(self.llm_base_url):
                raise ValueError("LLM_API_KEY is required for a hosted LLM endpoint")
        if not self.chunk_overlap_tokens < self.chunk_target_tokens <= self.chunk_max_tokens:
            raise ValueError("Chunk limits must satisfy overlap < target <= max")
        return self

    @model_validator(mode="after")
    def _validate_access_roles(self) -> "Settings":
        if not self.access_roles:
            raise ValueError("ACCESS_ROLES must define at least one role")
        for role, labels in self.access_roles.items():
            if "all" not in labels:
                raise ValueError(f"ACCESS_ROLES: role '{role}' must include the 'all' label")
        if self.access_default_role not in self.access_roles:
            raise ValueError(
                f"ACCESS_DEFAULT_ROLE '{self.access_default_role}' is not in ACCESS_ROLES"
            )
        return self

    @model_validator(mode="after")
    def _validate_accounts(self) -> "Settings":
        if self.budget_enabled and len(self.budget_ip_secret or "") < 32:
            raise ValueError("BUDGET_IP_SECRET must contain at least 32 characters")
        if self.accounts_enabled:
            for origin in [*self.auth_origin_list, *self.cors_origin_list, self.auth_public_url]:
                parsed = urlparse(origin)
                if (
                    parsed.scheme not in ("https", "http")
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.path not in ("", "/")
                    or parsed.query
                    or parsed.fragment
                    or (
                        parsed.scheme == "http"
                        and parsed.hostname not in ("localhost", "127.0.0.1")
                    )
                ):
                    raise ValueError(
                        "Auth origins must be exact HTTPS origins (HTTP localhost only)"
                    )
            if not self.auth_origin_list:
                raise ValueError("AUTH_ALLOWED_ORIGINS must list a trusted UI origin")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        return self

    @property
    def auth_origin_list(self) -> list[str]:
        return [
            value.strip().rstrip("/")
            for value in self.auth_allowed_origins.split(",")
            if value.strip()
        ]

    @property
    def google_available(self) -> bool:
        return self.accounts_enabled and bool(self.google_client_id and self.google_client_secret)

    @model_validator(mode="after")
    def _validate_google(self) -> "Settings":
        self.google_client_id = (self.google_client_id or "").strip() or None
        self.google_client_secret = (self.google_client_secret or "").strip() or None
        if bool(self.google_client_id) != bool(self.google_client_secret):
            raise ValueError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together"
            )
        endpoint = urlparse(self.google_redirect_uri)
        if (
            endpoint.scheme not in ("https", "http")
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.path != "/v1/auth/google/callback"
            or endpoint.query
            or endpoint.fragment
            or (endpoint.scheme == "http" and endpoint.hostname not in ("localhost", "127.0.0.1"))
        ):
            raise ValueError(
                "GOOGLE_REDIRECT_URI must be an exact HTTPS callback (HTTP localhost only)"
            )
        return self

    @property
    def registration_available(self) -> bool:
        return self.accounts_enabled and bool(self.smtp_host and self.smtp_from)

    @property
    def sync_database_url(self) -> str:
        if self.database_url_sync:
            return self.database_url_sync
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def max_upload_bytes(self) -> int:
        mb = self.max_upload_mb
        if self.demo_mode:
            mb = min(mb, self.demo_max_upload_mb)
        return mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def embedding_model_id(self) -> str:
        """Identifier stored on collections to prevent mixing embedding models."""
        if self.embedding_provider == "openai":
            return f"{self.openai_embedding_model}@{self.embedding_dim}"
        if self.embedding_provider == "ollama":
            return self.ollama_embedding_model
        return f"stub@{self.embedding_dim}"


@lru_cache
def get_settings() -> Settings:
    # required fields (database_url, redis_url) come from the environment / .env;
    # pydantic-settings raises a clear error at startup when they are missing
    return Settings()
