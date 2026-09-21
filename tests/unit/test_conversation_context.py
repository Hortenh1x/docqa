"""Safe conversation context serialization and strict follow-up normalization."""

import asyncio
import json
import uuid

import pytest

from app.access.roles import Principal
from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.conversations.context import (
    ConversationContext,
    SafeReference,
    SafeTurn,
    access_fingerprint,
    fit_safe_context,
)
from app.conversations.normalizer import (
    GENERIC_CLARIFICATION,
    build_normalizer_prompt,
    normalize_followup,
    parse_normalizer_output,
)
from app.generation.llm import GenerationError, StreamUsage, TextDelta
from app.retrieval.planning import UsageAccumulator


def snapshot(*, reset: bool = False) -> ConversationContext:
    return ConversationContext(
        conversation_id=uuid.uuid4(),
        parent_query_id=uuid.uuid4(),
        source_generation=7,
        access_fingerprint="fingerprint",
        reset=reset,
        turns=(
            SafeTurn(query_id=uuid.uuid4(), question="What was the 2017 card limit?"),
            SafeTurn(query_id=uuid.uuid4(), question="And what changed in 2022?"),
        ),
        references=(
            SafeReference(
                document_id=uuid.uuid4(),
                chunk_id=42,
                filename="rates.md",
                section="Historical rates",
            ),
        ),
    )


def test_access_fingerprint_is_canonical_and_excludes_actor_kind():
    employee = Principal("employee", ("managers", "all"))
    reordered = Principal("employee", ("all", "managers"))
    assert access_fingerprint(employee) == access_fingerprint(reordered)
    assert access_fingerprint(employee) != access_fingerprint(Principal("manager", employee.labels))


def test_safe_context_budget_counts_questions_and_reference_metadata():
    turns = [
        SafeTurn(uuid.uuid4(), "old " * 400),
        SafeTurn(uuid.uuid4(), "recent " * 40),
    ]
    references = [
        SafeReference(uuid.uuid4(), n, f"long-filename-{n}-" * 15, "section " * 30)
        for n in range(8)
    ]
    fitted = fit_safe_context(turns, references, token_budget=160, max_references=6)
    serialized = json.dumps(fitted.prompt_payload(), sort_keys=True, separators=(",", ":"))
    from app.ingestion.chunking import TokenCounter

    assert TokenCounter().count(serialized) <= 160
    assert len(fitted.references) <= 6
    assert not fitted.turns or fitted.turns[-1].question.startswith("recent")


def test_overlong_newest_parent_does_not_fall_back_to_an_older_subject():
    turns = [
        SafeTurn(uuid.uuid4(), "Tell me about Amazon"),
        SafeTurn(uuid.uuid4(), "Microsoft " * 1000),
    ]
    fitted = fit_safe_context(turns, [], token_budget=128, max_references=6)
    assert fitted.turns == ()


def test_budget_matches_exact_safe_context_shape_sent_to_normalizer():
    from app.ingestion.chunking import TokenCounter

    turn = SafeTurn(uuid.uuid4(), "x " * 1982)
    fitted = fit_safe_context([turn], [], token_budget=2000, max_references=6)
    context = ConversationContext(
        conversation_id=uuid.uuid4(),
        parent_query_id=turn.query_id,
        source_generation=1,
        access_fingerprint="fingerprint",
        reset=False,
        turns=fitted.turns,
        references=fitted.references,
    )
    serialized = json.dumps(
        context.prompt_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert TokenCounter().count(serialized) <= 2000


@pytest.mark.parametrize(
    ("raw", "action", "question"),
    [
        (
            '{"action":"search","effective_question":"Amazon revenue in 2022?"}',
            "search",
            "Amazon revenue in 2022?",
        ),
        (
            '{"action":"clarify","question":"Which company do you mean?"}',
            "clarify",
            "Which company do you mean?",
        ),
    ],
)
def test_strict_normalizer_parser_accepts_only_exact_shapes(raw, action, question):
    parsed = parse_normalizer_output(raw, max_question_chars=4000)
    assert parsed is not None
    assert parsed.action == action and parsed.question == question


@pytest.mark.parametrize(
    "raw",
    [
        "",
        '```json\n{"action":"search","effective_question":"x"}\n```',
        '{"action":"search","effective_question":"x"} trailing',
        '{"action":"search","effective_question":""}',
        '{"action":"search","effective_question":"x","extra":true}',
        '{"action":"clarify","effective_question":"x"}',
        '{"action":"search","effective_question":"x","effective_question":"y"}',
        '[{"action":"search","effective_question":"x"}]',
        '{"action":"answer","question":"x"}',
        "[" * 1100 + "]" * 1100,
        '{"action":"search","effective_question":1' + "0" * 5000 + "}",
    ],
)
def test_strict_normalizer_parser_rejects_malformed_extra_and_duplicate_fields(raw):
    assert parse_normalizer_output(raw, max_question_chars=4000) is None


def test_normalizer_prompt_contains_only_safe_untrusted_metadata():
    context = snapshot(reset=True)
    system, user = build_normalizer_prompt("And then?", context)
    assert "untrusted" in system.lower()
    assert "never" in system.lower() and "evidence" in system.lower()
    assert "What was the 2017 card limit?" in user
    assert "rates.md" in user and "Historical rates" in user
    assert "assistant answer secret" not in user
    assert "passage content secret" not in user
    assert "access_label" not in user and "quotes" not in user
    assert '"reset":true' in user


class StubNormalizer:
    model_name = "stub-normalizer"

    def __init__(self, events):
        self.events = events
        self.calls = 0
        self.prompts = []

    async def stream(self, system, user):
        self.calls += 1
        self.prompts.append((system, user))
        for event in self.events:
            if isinstance(event, BaseException):
                raise event
            yield event


async def test_normalizer_uses_one_stream_and_shared_usage_accumulator():
    provider = StubNormalizer(
        [
            TextDelta('{"action":"search","effective_question":"Amazon in 2022?"}'),
            StreamUsage(prompt_tokens=31, completion_tokens=9),
        ]
    )
    aggregate = UsageAccumulator()
    result = await normalize_followup(
        provider,
        "And in 2022?",
        snapshot(),
        aggregate_usage=aggregate,
        max_output_chars=8192,
        max_question_chars=4000,
    )
    assert result.action == "search" and result.question == "Amazon in 2022?"
    assert result.usage == StreamUsage(prompt_tokens=31, completion_tokens=9)
    assert aggregate.total == result.usage
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("current_question", "completion", "expected_action"),
    [
        (
            "And in 2022?",
            '{"action":"clarify","question":"Which subject do you mean?"}',
            "clarify",
        ),
        (
            "What was Amazon revenue in 2022?",
            '{"action":"search","effective_question":"What was Amazon revenue in 2022?"}',
            "search",
        ),
    ],
)
async def test_normalizer_runs_with_empty_history_after_reset(
    current_question, completion, expected_action
):
    context = ConversationContext(
        conversation_id=uuid.uuid4(),
        parent_query_id=uuid.uuid4(),
        source_generation=8,
        access_fingerprint="new-access",
        reset=True,
        turns=(),
        references=(),
    )
    provider = StubNormalizer([TextDelta(completion)])
    result = await normalize_followup(provider, current_question, context)
    assert result.action == expected_action
    assert provider.calls == 1
    assert '"reset":true' in provider.prompts[0][1]


@pytest.mark.parametrize(
    "events",
    [
        [TextDelta("not json")],
        [TextDelta(" ")],
        [TextDelta('{"action":"search","effective_question":"' + "x" * 5000 + '"}')],
    ],
)
async def test_invalid_or_oversized_completion_becomes_controlled_clarification(events):
    provider = StubNormalizer(events)
    result = await normalize_followup(
        provider,
        "And then?",
        snapshot(),
        max_output_chars=512,
        max_question_chars=4000,
    )
    assert result.action == "clarify"
    assert result.question == GENERIC_CLARIFICATION
    assert result.controlled is True
    assert provider.calls == 1


@pytest.mark.parametrize(
    "error",
    [
        GenerationError("provider failed"),
        BudgetExceededError("budget denied"),
        BudgetUnavailableError("accounting unavailable"),
        asyncio.CancelledError(),
    ],
)
async def test_provider_and_cancellation_errors_propagate(error):
    provider = StubNormalizer([error])
    with pytest.raises(type(error)):
        await normalize_followup(provider, "And then?", snapshot())
