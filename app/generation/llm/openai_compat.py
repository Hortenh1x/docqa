"""OpenAI-compatible chat completions over a configurable base_url.

One class, four backends: OpenAI, DeepSeek, Ollama (/v1), vLLM — anything that speaks
the /chat/completions SSE dialect. ``stream_options.include_usage`` yields exact token
counts in the final chunk on providers that support it; absent usage degrades to NULL
cost, never to a failure.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.billing.providers import after_call, before_call
from app.config import is_local_llm_url
from app.generation.llm.base import GenerationError, JsonResult, LLMEvent, StreamUsage, TextDelta

_TIMEOUT = httpx.Timeout(180.0, connect=10.0)


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,  # tests inject a MockTransport
        total_timeout_s: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._transport = transport
        self.total_timeout_s = total_timeout_s

    @property
    def model_name(self) -> str:
        return self.model

    async def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]:
        ticket = None
        if not is_local_llm_url(self.base_url):
            ticket = await before_call(self.model, [system, user], self.max_tokens)
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
                asyncio.timeout(self.total_timeout_s),
                httpx.AsyncClient(timeout=_TIMEOUT, transport=self._transport) as client,
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
                        await after_call(
                            ticket,
                            self.model,
                            usage.get("prompt_tokens"),
                            usage.get("completion_tokens"),
                        )
                        yield StreamUsage(
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                        )
        except TimeoutError as exc:
            raise GenerationError("LLM total deadline exceeded.") from exc
        except httpx.HTTPError as exc:
            raise GenerationError(f"LLM request failed: {exc}") from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise GenerationError(f"LLM stream malformed: {exc}") from exc

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int
    ) -> JsonResult:
        """Structured output: ``json_schema`` response format first; providers that reject
        it (400) get ``json_object`` with the schema spelled out in the prompt. A reply
        that is not valid JSON is sent back once for repair."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        formats: list[dict[str, Any]] = [
            {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema, "strict": False},
            },
            {"type": "json_object"},
        ]
        prompt_total = 0
        completion_total = 0
        usage_seen = False
        try:
            async with (
                asyncio.timeout(self.total_timeout_s),
                httpx.AsyncClient(timeout=_TIMEOUT, transport=self._transport) as client,
            ):
                response_format = formats[0]
                repairs = 0
                while True:
                    payload = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0,
                        "max_tokens": max_tokens,
                        "response_format": response_format,
                    }
                    ticket = None
                    if not is_local_llm_url(self.base_url):
                        # Both the schema and any repair messages count toward input usage.
                        texts = [message["content"] for message in messages]
                        texts.append(json.dumps(response_format))
                        ticket = await before_call(self.model, texts, max_tokens)
                    usage: dict[str, Any] = {}
                    try:
                        response = await client.post(
                            f"{self.base_url}/chat/completions", json=payload, headers=headers
                        )
                        if response.status_code == 200:
                            body = response.json()
                            usage = body.get("usage") or {}
                    finally:
                        # Settle this HTTP attempt before admitting another one. Unknown
                        # usage keeps its reservation instead of borrowing a later reply's.
                        await after_call(
                            ticket,
                            self.model,
                            usage.get("prompt_tokens"),
                            usage.get("completion_tokens"),
                        )
                    if response.status_code == 400 and response_format is formats[0]:
                        response_format = formats[1]
                        messages[0] = {
                            "role": "system",
                            "content": system
                            + "\n\nAnswer with one JSON object matching this JSON Schema:\n"
                            + json.dumps(schema),
                        }
                        continue
                    if response.status_code != 200:
                        raise GenerationError(
                            f"LLM returned {response.status_code}: {response.text[:500]}"
                        )
                    if usage:
                        usage_seen = True
                        prompt_total += int(usage.get("prompt_tokens") or 0)
                        completion_total += int(usage.get("completion_tokens") or 0)
                    content = (body["choices"][0]["message"] or {}).get("content") or ""
                    parsed = _parse_json_object(content)
                    if parsed is not None:
                        break
                    if repairs >= 1:
                        raise GenerationError("LLM did not return a JSON object.")
                    repairs += 1
                    messages = messages + [
                        {"role": "assistant", "content": content[:4000]},
                        {
                            "role": "user",
                            "content": "That was not valid JSON. Return only the JSON object.",
                        },
                    ]
        except TimeoutError as exc:
            raise GenerationError("LLM total deadline exceeded.") from exc
        except httpx.HTTPError as exc:
            raise GenerationError(f"LLM request failed: {exc}") from exc
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise GenerationError(f"LLM response malformed: {exc}") from exc
        return JsonResult(
            content=parsed,
            prompt_tokens=prompt_total if usage_seen else None,
            completion_tokens=completion_total if usage_seen else None,
        )


def _parse_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
