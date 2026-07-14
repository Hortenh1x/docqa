"""Deterministic LLM stub, scenario-switched by question keywords:

- "sabbatical" / "no_answer"  -> the NO_ANSWER sentinel (generation-gate test)
- "badcite"                    -> an answer citing a non-existent block [9]
- anything else                -> a grounded answer citing [1]

Answers stream in several deltas on purpose. ``calls`` counts invocations so tests can
assert the refusal gate spent zero LLM calls.
"""

from collections.abc import AsyncIterator
from typing import ClassVar

from app.generation.llm.base import LLMEvent, StreamUsage, TextDelta


class StubLLM:
    calls: ClassVar[int] = 0

    @property
    def model_name(self) -> str:
        return "stub"

    async def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]:
        type(self).calls += 1
        question = user.rsplit("Question:", 1)[-1].lower()

        if "sabbatical" in question or "no_answer" in question:
            yield TextDelta("NO_ANS")
            yield TextDelta("WER")
            yield StreamUsage(prompt_tokens=50, completion_tokens=3)
            return
        if "badcite" in question:
            yield TextDelta("Employees receive 27 vacation days [1]")
            yield TextDelta(" as stated in the handbook [9].")
            yield StreamUsage(prompt_tokens=120, completion_tokens=16)
            return
        yield TextDelta("Employees receive 27 vacation days per year [1]")
        yield TextDelta(", and unused days expire on March 31 [1].")
        yield StreamUsage(prompt_tokens=100, completion_tokens=18)
