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
        return self.max_upload_mb * 1024 * 1024

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
