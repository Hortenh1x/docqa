"""Deterministic LLM stub, scenario-switched by question keywords:

- "sabbatical" / "no_answer"  -> the NO_ANSWER sentinel (generation-gate test)
- "badcite"                    -> an answer citing a non-existent block [9]
- anything else                -> a grounded answer citing [1], followed by a QUOTES section

Answers stream in several deltas on purpose. ``calls`` counts invocations so tests can
assert the refusal gate spent zero LLM calls.
"""

import json
import re
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from app.generation.llm.base import JsonResult, LLMEvent, StreamUsage, TextDelta

_RESTRICTED_EXCERPT_RE = re.compile(
    r"^### .+ \(Access: \w+\)\n(.+?)(?=\n\n### |\n\nWrite )", re.M | re.S
)


class StubLLM:
    calls: ClassVar[int] = 0

    @property
    def model_name(self) -> str:
        return "stub"

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int
    ) -> JsonResult:
        """Field extraction stand-in: for every field of the response schema, find a
        ``<label>: value`` line in the document text (label = field name with spaces, or
        its description) and return the value with that line as the quote."""
        type(self).calls += 1
        fields = (schema.get("properties") or {}).get("fields", {}).get("properties") or {}
        document = user.split("DOCUMENT:", 1)[-1]
        out: dict[str, Any] = {}
        for name, spec in fields.items():
            labels = [name.replace("_", " ")]
            description = str(spec.get("description") or "")
            if description:
                labels.append(description.split(".")[0])
            value: Any = None
            quote: str | None = None
            for label in labels:
                pattern = re.compile(
                    rf"^[^\n]*\b{re.escape(label)}\b\s*[:\-–]\s*(.+?)\s*$", re.I | re.M
                )
                match = pattern.search(document)
                if match:
                    value, quote = match.group(1).strip(), match.group(0).strip()
                    break
            out[name] = {"value": value, "quote": quote}
        return JsonResult(content={"fields": out}, prompt_tokens=200, completion_tokens=60)

    async def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]:
        type(self).calls += 1

        if "retrieval planner for a grounded document question-answering system" in system:
            yield TextDelta('{"queries":[]}')
            yield StreamUsage(prompt_tokens=0, completion_tokens=0)
            return

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
        # the pinpoint section (prompt rule 7), with the marker split across deltas —
        # the pipeline must keep every character of it out of the streamed answer
        yield TextDelta("\n\nQUO")
        yield TextDelta('TES:\n[1] "Employees receive 27 vacation days per year"\n')
        yield StreamUsage(prompt_tokens=100, completion_tokens=18)
