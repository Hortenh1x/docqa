"""Deterministic reranker for tests: score = share of question words present in the chunk.

Gives real control over the refusal gate in tests without any network: overlapping
questions score high, off-corpus questions score near zero.
"""

import re
from dataclasses import replace

from app.retrieval.base import RetrievedChunk

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁäöüÄÖÜß0-9]+")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


class StubRerank:
    async def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        question_words = _words(question)
        if not question_words:
            return [replace(c, score=0.0) for c in chunks[:top_n]]
        scored = [
            replace(c, score=len(question_words & _words(c.content)) / len(question_words))
            for c in chunks
        ]
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_n]
