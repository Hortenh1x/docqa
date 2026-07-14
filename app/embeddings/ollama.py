"""Ollama embeddings (e.g. bge-m3, natively 1024-dim) — local, zero-cost development."""

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.embeddings.base import EmbeddingError, check_dim

_TIMEOUT = httpx.Timeout(120.0, connect=5.0)  # first call may load the model into memory


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class OllamaEmbeddings:
    def __init__(self, base_url: str, model: str, dim: int, batch_size: int = 64) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                for start in range(0, len(texts), self.batch_size):
                    batch = texts[start : start + self.batch_size]
                    vectors.extend(await self._embed_batch(client, batch))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise EmbeddingError(f"ollama embeddings failed: {exc}") from exc
        return check_dim(vectors, self.dim)

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _embed_batch(self, client: httpx.AsyncClient, batch: list[str]) -> list[list[float]]:
        response = await client.post(
            f"{self.base_url}/api/embed", json={"model": self.model, "input": batch}
        )
        response.raise_for_status()
        embeddings = response.json()["embeddings"]
        if len(embeddings) != len(batch):
            raise EmbeddingError(
                f"ollama returned {len(embeddings)} vectors for {len(batch)} inputs"
            )
        return [list(map(float, vector)) for vector in embeddings]
