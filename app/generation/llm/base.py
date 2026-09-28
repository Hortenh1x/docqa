"""LLM provider protocol: a stream of text deltas, ending with a usage event."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings, is_local_llm_url


class GenerationError(Exception):
    """LLM call failed (network, auth, provider error)."""


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class StreamUsage:
    prompt_tokens: int | None
    completion_tokens: int | None


LLMEvent = TextDelta | StreamUsage


@dataclass(frozen=True)
class JsonResult:
    """A structured (JSON) completion with its usage."""

    content: dict[str, Any]
    prompt_tokens: int | None
    completion_tokens: int | None


class LLMProvider(Protocol):
    def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]: ...

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int
    ) -> JsonResult:
        """One non-streaming call whose answer must be a JSON object matching ``schema``."""
        ...

    @property
    def model_name(self) -> str: ...


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compat":
        # hosted endpoints reject keyless requests anyway — fail fast and readable
        # instead of surfacing a 401 as provider_unavailable at query time
        if not settings.llm_api_key and not is_local_llm_url(settings.llm_base_url):
            raise RuntimeError(
                f"LLM_API_KEY is required for hosted endpoint {settings.llm_base_url!r} "
                "(only local Ollama/vLLM endpoints may go keyless)"
            )
        from app.generation.llm.openai_compat import OpenAICompatLLM

        return OpenAICompatLLM(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            total_timeout_s=settings.llm_timeout_s,
        )
    from app.generation.llm.stub import StubLLM

    return StubLLM()
