"""Cohere rerank (multilingual — covers the German part of the corpus).

Graceful degradation is the contract: on timeout/429/5xx the search must not fail,
so we log and fall back to the fused (RRF) order.
"""

from dataclasses import replace

import httpx
import structlog

from app.retrieval.base import RetrievedChunk

log = structlog.get_logger("docqa.rerank")

_MAX_DOC_CHARS = 4000


class CohereRerank:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float,
        base_url: str = "https://api.cohere.com/v2",
        transport: httpx.AsyncBaseTransport | None = None,  # tests inject a MockTransport
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    async def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/rerank",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "query": question,
                        "documents": [c.content[:_MAX_DOC_CHARS] for c in chunks],
                        "top_n": top_n,
                    },
                )
                response.raise_for_status()
                results = response.json()["results"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("rerank_degraded", provider="cohere", error=str(exc), reranked=False)
            return chunks[:top_n]
        return [
            replace(chunks[item["index"]], score=float(item["relevance_score"])) for item in results
        ]
