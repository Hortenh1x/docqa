"""LLM access for the corpus tooling: the project's OpenAI-compatible provider, non-thinking model."""  # noqa: E501

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.generation.llm import GenerationError, TextDelta
from app.generation.llm.openai_compat import OpenAICompatLLM

DEFAULT_MODEL = "deepseek-chat"  # the non-thinking alias: no hidden-reasoning budget burns


def make_llm(
    model: str | None = None, temperature: float = 0.7, max_tokens: int = 6000
) -> OpenAICompatLLM:
    settings = get_settings()
    return OpenAICompatLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=model or DEFAULT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def complete(llm: OpenAICompatLLM, system: str, user: str, attempts: int = 4) -> str:
    """Collect a completion; retries transient provider errors with backoff."""
    for attempt in range(attempts):
        try:
            parts: list[str] = []
            async for event in llm.stream(system, user):
                if isinstance(event, TextDelta):
                    parts.append(event.text)
            text = "".join(parts).strip()
            if text:
                return text
        except GenerationError as exc:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(3 * 2**attempt)
            print(f"  provider error, retrying: {exc}")
    raise GenerationError("empty completion")
