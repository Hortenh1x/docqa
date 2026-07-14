from app.config import Settings
from app.embeddings.base import EmbeddingError, EmbeddingProvider
from app.embeddings.ollama import OllamaEmbeddings
from app.embeddings.openai import OpenAIEmbeddings
from app.embeddings.stub import StubEmbeddings

__all__ = [
    "EmbeddingError",
    "EmbeddingProvider",
    "OllamaEmbeddings",
    "OpenAIEmbeddings",
    "StubEmbeddings",
    "get_embedding_provider",
]


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        return OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
            dim=settings.embedding_dim,
            batch_size=settings.embed_batch_size,
        )
    if settings.embedding_provider == "ollama":
        return OllamaEmbeddings(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embedding_model,
            dim=settings.embedding_dim,
            batch_size=settings.embed_batch_size,
        )
    return StubEmbeddings(dim=settings.embedding_dim)
