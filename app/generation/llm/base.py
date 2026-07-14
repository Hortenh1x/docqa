"""LLM provider protocol: a stream of text deltas, ending with a usage event."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings


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


class LLMProvider(Protocol):
    def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]: ...

    @property
    def model_name(self) -> str: ...


def _is_local(base_url: str) -> bool:
    return "localhost" in base_url or "127.0.0.1" in base_url or "host.docker.internal" in base_url


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compat":
        # hosted endpoints reject keyless requests anyway — fail fast and readable
        # instead of surfacing a 401 as provider_unavailable at query time
        if not settings.llm_api_key and not _is_local(settings.llm_base_url):
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
        )
    from app.generation.llm.stub import StubLLM

    return StubLLM()
