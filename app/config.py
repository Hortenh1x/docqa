"""Application settings. Fail fast: missing required variables abort startup."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # core — required, no defaults
    database_url: str
    redis_url: str
    # sync DSN for the Celery worker; derived from database_url when unset
    database_url_sync: str | None = None

    # embeddings
    embedding_provider: Literal["stub", "openai", "ollama"] = "stub"
    embedding_dim: int = 1024
    embed_batch_size: int = 64
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "bge-m3"

    # chunking
    chunk_target_tokens: int = 450
    chunk_overlap_tokens: int = 60
    chunk_max_tokens: int = 512

    # retrieval (tuned against the eval set in week 4)
    top_k_vector: int = 30
    top_k_fts: int = 30
    rrf_k: int = 60
    rrf_top_n: int = 20
    rerank_top_n: int = 8
    hnsw_ef_search: int = 100
    # tuned against eval/golden.yaml for the rerank=none cosine gate (see eval/results.md);
    # retune when switching to a real reranker — their score scales differ
    refusal_threshold: float = 0.50

    # reranking
    rerank_provider: Literal["cohere", "local", "none", "stub"] = "none"
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-v3.5"
    rerank_timeout_s: float = 4.0

    # generation
    llm_provider: Literal["openai_compat", "stub"] = "stub"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    context_token_budget: int = 3600
    context_chunk_max_tokens: int = 700

    # rate limiting (token bucket per API key, by endpoint class)
    rate_limit_enabled: bool = True
    rate_limit_query_per_minute: int = 30
    rate_limit_upload_per_minute: int = 10
    rate_limit_default_per_minute: int = 120

    # idempotency
    idempotency_ttl_s: int = 86400

    # public demo mode: read-only demo collections + a small sandbox
    demo_mode: bool = False
    demo_max_files_per_collection: int = 5
    demo_max_upload_mb: int = 5

    # CORS (comma-separated origins for the UI)
    cors_origins: str = "http://localhost:3000"

    # limits
    max_upload_mb: int = 25
    max_pages: int = 300

    # misc
    storage_dir: Path = Path("data/files")
    log_level: str = "INFO"

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
