"""Deterministic LLM stub, scenario-switched by question keywords:

- "sabbatical" / "no_answer"  -> the NO_ANSWER sentinel (generation-gate test)
- "badcite"                    -> an answer citing a non-existent block [9]
- anything else                -> a grounded answer citing [1]

Answers stream in several deltas on purpose. ``calls`` counts invocations so tests can
assert the refusal gate spent zero LLM calls.
"""

import json
import re
from collections.abc import AsyncIterator
from typing import ClassVar

from app.generation.llm.base import LLMEvent, StreamUsage, TextDelta

_RESTRICTED_EXCERPT_RE = re.compile(
    r"^### .+ \(Access: \w+\)\n(.+?)(?=\n\n### |\n\nWrite )", re.M | re.S
)


class StubLLM:
    calls: ClassVar[int] = 0

    @property
    def model_name(self) -> str:
        return "stub"

    async def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]:
        type(self).calls += 1

        if "suggested questions" in system.lower():
            # candidates for app/generation/suggestions.py — valid JSON across deltas
            yield TextDelta('["What is the vacation policy?", ')
            yield TextDelta('"How many remote days are allowed?", ')
            yield TextDelta('"What is the travel allowance for France?", ')
            yield TextDelta('"When do unused vacation days expire?", ')
            yield TextDelta('"Who approves business trips?"')
            # access levels test hook: a restricted excerpt is echoed verbatim as a
            # candidate, so stub embeddings ground it (cosine 1.0) only under roles that
            # may read it → the suggestion gets a min_role above the default
            restricted = _RESTRICTED_EXCERPT_RE.search(user)
            if restricted:
                yield TextDelta(f", {json.dumps(restricted.group(1).strip())}")
            yield TextDelta("]")
            yield StreamUsage(prompt_tokens=60, completion_tokens=40)
            return

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
