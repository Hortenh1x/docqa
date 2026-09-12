"""openai_compat stream parsing against an httpx MockTransport (no network)."""

import httpx
import pytest

from app.generation.llm.base import GenerationError, StreamUsage, TextDelta
from app.generation.llm.openai_compat import OpenAICompatLLM


def make_llm(handler) -> OpenAICompatLLM:
    return OpenAICompatLLM(
        base_url="https://llm.test/v1",
        api_key="k",
        model="test-model",
        temperature=0.1,
        max_tokens=100,
        transport=httpx.MockTransport(handler),
    )


def sse_response(*frames: str) -> httpx.Response:
    body = "".join(f"data: {frame}\n\n" for frame in frames)
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


async def collect(llm: OpenAICompatLLM):
    return [event async for event in llm.stream("system", "user")]


async def test_parses_deltas_and_usage():
    llm = make_llm(
        lambda request: sse_response(
            '{"choices": [{"delta": {"content": "Employees get"}}]}',
            '{"choices": [{"delta": {"content": " 27 days [1]."}}]}',
            '{"choices": [], "usage": {"prompt_tokens": 42, "completion_tokens": 7}}',
            "[DONE]",
        )
    )
    events = await collect(llm)

    assert events == [
        TextDelta("Employees get"),
        TextDelta(" 27 days [1]."),
        StreamUsage(prompt_tokens=42, completion_tokens=7),
    ]


async def test_request_payload_and_auth_header():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = request.read()
        return sse_response("[DONE]")

    llm = make_llm(handler)
    await collect(llm)

    assert seen["auth"] == "Bearer k"
    body = seen["json"].decode()
    assert '"stream":true' in body
    assert '"include_usage":true' in body


async def test_http_error_becomes_generation_error():
    llm = make_llm(lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(GenerationError, match="500"):
        await collect(llm)


async def test_malformed_stream_becomes_generation_error():
    llm = make_llm(lambda request: sse_response("{not json"))
    with pytest.raises(GenerationError, match="malformed"):
        await collect(llm)


async def test_heartbeat_stream_has_a_total_deadline():
    import asyncio

    class Heartbeats(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield b": heartbeat\n\n"

    llm = make_llm(lambda _: httpx.Response(200, stream=Heartbeats()))
    llm.total_timeout_s = 0.03
    with pytest.raises(GenerationError, match="deadline"):
        await collect(llm)
