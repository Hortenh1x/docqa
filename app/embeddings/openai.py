"""OpenAI embeddings via plain httpx (no SDK dependency).

``text-embedding-3-*`` models support matryoshka truncation — ``dimensions=1024`` keeps
the schema-wide vector(1024) contract regardless of the model's native size.
"""

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.embeddings.base import EmbeddingError, check_dim

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and (
        exc.response.status_code == 429 or exc.response.status_code >= 500
    )


class OpenAIEmbeddings:
    def __init__(
        self,
        api_key: str,
        model: str,
        dim: int,
        batch_size: int = 64,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.batch_size = batch_size
        self.base_url = base_url.rstrip("/")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                for start in range(0, len(texts), self.batch_size):
                    batch = texts[start : start + self.batch_size]
                    vectors.extend(await self._embed_batch(client, batch))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise EmbeddingError(f"openai embeddings failed: {exc}") from exc
        return check_dim(vectors, self.dim)

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _embed_batch(self, client: httpx.AsyncClient, batch: list[str]) -> list[list[float]]:
        response = await client.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": batch, "dimensions": self.dim},
        )
        response.raise_for_status()
        data = response.json()["data"]
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]
