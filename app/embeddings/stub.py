"""Deterministic stub embeddings: a normalized vector derived from sha256 of the text.

Identical texts always produce identical vectors, so tests can assert retrieval
behaviour without any network. Not semantically meaningful by design.
"""

import hashlib
import math
import struct


class StubEmbeddings:
    def __init__(self, dim: int) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode()).digest()
        values: list[float] = []
        counter = 0
        while len(values) < self.dim:
            block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for (raw,) in struct.iter_unpack(">I", block):
                values.append(raw / 0xFFFFFFFF * 2.0 - 1.0)  # map uint32 -> [-1, 1]
                if len(values) == self.dim:
                    break
            counter += 1
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
