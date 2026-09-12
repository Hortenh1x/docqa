import uuid
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.generation import service
from app.generation.llm import TextDelta
from app.generation.prompts import build_user_prompt
from app.retrieval.base import RetrievedChunk
from app.retrieval.service import RetrievalResult
from eval import run_eval


@pytest.mark.asyncio
async def test_observer_captures_exact_trimmed_context_sent_to_model(monkeypatch):
    chunk = RetrievedChunk(
        chunk_id=41,
        document_id=uuid.uuid4(),
        filename="synthetic.txt",
        content="visible " * 200 + "EXCLUDED_TAIL",
        score=0.9,
        page_start=None,
        page_end=None,
        section_path="Policy",
    )
    monkeypatch.setattr(service, "retrieve", AsyncMock(return_value=RetrievalResult([chunk], 0.9)))
    monkeypatch.setattr(service, "_record_query", AsyncMock())
    prompts = []

    class Model:
        model_name = "stub"

        async def stream(self, system, user):
            prompts.append(user)
            yield TextDelta("The policy is visible [1].")

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: Model())
    captured = []
    settings = Settings(_env_file=None, context_chunk_max_tokens=20)
    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(),
            uuid.uuid4(),
            "Policy?",
            settings,
            data_version=0,
            context_observer=captured.extend,
        )
    ]
    assert any(isinstance(event, service.DoneEvent) for event in events)
    assert len(captured) == 1
    assert "EXCLUDED_TAIL" not in captured[0].text
    assert prompts == [build_user_prompt(captured, "Policy?")]


@pytest.mark.asyncio
async def test_judge_uses_original_context_without_second_retrieval(monkeypatch):
    monkeypatch.setattr(run_eval, "get_settings", lambda: Settings(_env_file=None))
    retrieval = AsyncMock(side_effect=AssertionError("must not retrieve twice"))
    monkeypatch.setattr(run_eval, "retrieve", retrieval)
    prompts = []

    class Judge:
        model = "stub"

        def __init__(self, **kwargs):
            pass

        async def stream(self, system, user):
            prompts.append(user)
            yield TextDelta('{"faithful": true, "correct": true}')

    monkeypatch.setattr(run_eval, "OpenAICompatLLM", Judge)
    result = run_eval.QuestionResult("one", "direct", "Policy?", [], False, "Visible")
    run_eval._record_answer(
        result,
        {
            "answer": "Visible [1]",
            "refused": False,
            "context_blocks": [{"n": 1, "text": "ACTUAL_TRIMMED_CONTEXT", "chunk_id": 41}],
        },
    )
    unavailable = run_eval.QuestionResult("http", "direct", "Policy?", [], False, "Visible")
    run_eval._record_answer(unavailable, {"answer": "Visible [1]", "refused": False})
    await run_eval.run_judge_layer(uuid.uuid4(), None, [result, unavailable], None, "employee")
    assert len(prompts) == 1 and "ACTUAL_TRIMMED_CONTEXT" in prompts[0]
    assert result.judge_faithful is True
    assert unavailable.judge_faithful is None
    assert unavailable.judge_skip_reason == "original_context_unavailable"
    retrieval.assert_not_called()
