"""Structured-response retries must each pass spending admission."""

import json
import uuid

import httpx
import pytest

from app.billing.errors import BudgetExceededError
from app.generation.llm import openai_compat


def reply(content, prompt=10, completion=5):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        },
    )


def llm(handler):
    return openai_compat.OpenAICompatLLM(
        "https://llm.test/v1",
        None,
        "test",
        0,
        100,
        transport=httpx.MockTransport(handler),
    )


async def test_repair_is_admitted_and_settled_separately(monkeypatch):
    events = []
    admissions = []

    async def reserve(model, texts, max_output):
        ticket = uuid.uuid4()
        admissions.append((ticket, texts))
        events.append("reserve")
        return ticket

    async def settle(ticket, model, prompt, completion):
        events.append((ticket, prompt, completion))

    monkeypatch.setattr(openai_compat, "before_call", reserve)
    monkeypatch.setattr(openai_compat, "after_call", settle)
    responses = iter([reply("invalid"), reply('{"ok":true}', 20, 8)])
    result = await llm(lambda _: next(responses)).complete_json(
        "system", "question", {"type": "object"}, max_tokens=100
    )
    assert len(admissions) == 2
    assert events == ["reserve", (admissions[0][0], 10, 5), "reserve", (admissions[1][0], 20, 8)]
    assert "invalid" in admissions[1][1]
    assert (result.prompt_tokens, result.completion_tokens) == (30, 13)


async def test_repair_cannot_spend_after_budget_exhausted(monkeypatch):
    calls = []
    reservations = 0

    async def reserve(*args):
        nonlocal reservations
        reservations += 1
        if reservations == 2:
            raise BudgetExceededError()
        return uuid.uuid4()

    async def settle(*args):
        pass

    def respond(request):
        calls.append(request)
        return reply("invalid" if len(calls) == 1 else "{}")

    monkeypatch.setattr(openai_compat, "before_call", reserve)
    monkeypatch.setattr(openai_compat, "after_call", settle)
    with pytest.raises(BudgetExceededError):
        await llm(respond).complete_json("sys", "user", {}, max_tokens=100)
    assert len(calls) == 1


async def test_response_schema_is_included_in_admission(monkeypatch):
    estimates = []

    async def reserve(model, texts, output):
        estimates.append("\n".join(texts))

    monkeypatch.setattr(openai_compat, "before_call", reserve)
    schema = {"type": "object", "description": "x" * 5000}
    await llm(lambda _: reply("{}")).complete_json("sys", "user", schema, max_tokens=100)
    assert json.dumps(schema) in estimates[0]


async def test_format_fallback_does_not_consume_json_repair(monkeypatch):
    estimates = []

    async def reserve(model, texts, output):
        estimates.append("\n".join(texts))

    monkeypatch.setattr(openai_compat, "before_call", reserve)
    responses = iter([httpx.Response(400), reply("invalid"), reply('{"ok":true}')])
    result = await llm(lambda _: next(responses)).complete_json(
        "sys", "user", {"type": "object"}, max_tokens=100
    )
    assert result.content == {"ok": True}
    assert len(estimates) == 3
    assert "matching this JSON Schema" in estimates[1]
