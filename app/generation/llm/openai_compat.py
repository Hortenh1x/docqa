"""OpenAI-compatible chat completions over a configurable base_url.

One class, four backends: OpenAI, DeepSeek, Ollama (/v1), vLLM — anything that speaks
the /chat/completions SSE dialect. ``stream_options.include_usage`` yields exact token
counts in the final chunk on providers that support it; absent usage degrades to NULL
cost, never to a failure.
"""

import json
from collections.abc import AsyncIterator

import httpx

from app.generation.llm.base import GenerationError, LLMEvent, StreamUsage, TextDelta

_TIMEOUT = httpx.Timeout(180.0, connect=10.0)


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def model_name(self) -> str:
        return self.model

    async def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            async with (
                httpx.AsyncClient(timeout=_TIMEOUT) as client,
                client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
                ) as response,
            ):
                if response.status_code != 200:
                    body = (await response.aread()).decode(errors="replace")[:500]
                    raise GenerationError(f"LLM returned {response.status_code}: {body}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    choices = event.get("choices") or []
                    if choices:
                        delta = (choices[0].get("delta") or {}).get("content")
                        if delta:
                            yield TextDelta(delta)
                    usage = event.get("usage")
                    if usage:
                        yield StreamUsage(
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                        )
        except httpx.HTTPError as exc:
            raise GenerationError(f"LLM request failed: {exc}") from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise GenerationError(f"LLM stream malformed: {exc}") from exc
