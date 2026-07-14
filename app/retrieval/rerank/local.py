"""Local cross-encoder reranker (BAAI/bge-reranker-v2-m3) — fully offline mode.

Honest performance note: on CPU, 20 pairs take roughly 1–3 s; for a production demo
prefer Cohere (or export the model to ONNX int8). The dependency is intentionally not
installed by default (it drags in torch): ``uv pip install sentence-transformers``.
The model is a lazy singleton loaded on first use.
"""

from dataclasses import replace
from typing import Any

import anyio

from app.retrieval.base import RetrievedChunk

_MAX_DOC_CHARS = 1500
_MODEL_NAME = "BAAI/bge-reranker-v2-m3"

_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise RuntimeError(
                "RERANK_PROVIDER=local requires sentence-transformers: "
                "uv pip install sentence-transformers"
            ) from exc
        _model = CrossEncoder(_MODEL_NAME, max_length=512)
    return _model


def _predict(question: str, chunks: list[RetrievedChunk]) -> list[float]:
    model = _get_model()
    pairs = [(question, c.content[:_MAX_DOC_CHARS]) for c in chunks]
    return [float(s) for s in model.predict(pairs)]


class LocalRerank:
    async def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        scores = await anyio.to_thread.run_sync(_predict, question, chunks)
        scored = [replace(c, score=s) for c, s in zip(chunks, scores, strict=True)]
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_n]
