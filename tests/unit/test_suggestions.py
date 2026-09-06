"""Suggested-questions building blocks: parsing, prompt, stub-LLM drafting."""

from app.config import Settings
from app.generation.suggestions import (
    MAX_QUESTION_CHARS,
    SUGGESTIONS_SYSTEM,
    build_suggestions_prompt,
    choose_min_role,
    draft_candidates,
    drop_leaky,
    parse_questions,
    select_final,
)


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        redis_url="redis://localhost:6379/0",
        embedding_provider="stub",
        llm_provider="stub",
    )


class TestParseQuestions:
    def test_clean_json_array(self):
        raw = '["How many vacation days?", "What is the travel allowance?"]'
        assert parse_questions(raw) == [
            "How many vacation days?",
            "What is the travel allowance?",
        ]

    def test_code_fences_and_prose_tolerated(self):
        raw = 'Sure! Here you go:\n```json\n["Q one?", "Q two?"]\n```\nHope that helps.'
        assert parse_questions(raw) == ["Q one?", "Q two?"]

    def test_whitespace_normalized_and_duplicates_dropped(self):
        raw = '["  How\\n many days? ", "how many days?", "Other?"]'
        assert parse_questions(raw) == ["How many days?", "Other?"]

    def test_non_string_items_skipped(self):
        raw = '["Real question?", 42, {"q": "no"}, null]'
        assert parse_questions(raw) == ["Real question?"]

    def test_overlong_question_dropped(self):
        raw = f'["{"x" * (MAX_QUESTION_CHARS + 1)}", "Short?"]'
        assert parse_questions(raw) == ["Short?"]

    def test_garbage_returns_empty(self):
        assert parse_questions("") == []
        assert parse_questions("no json here") == []
        assert parse_questions("[not valid json]") == []
        assert parse_questions('{"a": 1}') == []


def test_prompt_carries_excerpts_and_count():
    prompt = build_suggestions_prompt(["### a.md\nAlpha", "### b.md\nBeta"], 5)
    assert "### a.md\nAlpha" in prompt
    assert "### b.md\nBeta" in prompt
    assert "5 candidate questions" in prompt
    assert "JSON array" in prompt


def test_system_prompt_matches_stub_marker():
    # the stub LLM switches on this phrase — keep them in sync
    assert "suggested questions" in SUGGESTIONS_SYSTEM.lower()


async def test_draft_candidates_with_stubs():
    questions, embeddings = await draft_candidates(_settings(), ["### a.md\nVacation: 27 days."])
    assert len(questions) == 5  # the stub yields five candidates
    assert len(embeddings) == len(questions)
    assert all(len(e) == 1024 for e in embeddings)


# --- access levels ---


def test_leaky_questions_are_dropped():
    questions = [
        "What is the card limit?",
        "Is the card limit 1500?",
        "Is the per-diem €28?",
        "How much is the $ allowance?",
        "Wie hoch ist die Pauschale?",
    ]
    assert drop_leaky(questions) == ["What is the card limit?", "Wie hoch ist die Pauschale?"]


ROLES = ["employee", "manager", "hr", "finance", "leadership"]


def test_min_role_is_the_least_privileged_role_passing_the_gate():
    scores = {"employee": 0.2, "manager": 0.2, "hr": 0.2, "finance": 0.9, "leadership": 0.9}
    assert choose_min_role(scores, ROLES, 0.5, "employee") == "finance"


def test_min_role_needs_the_role_to_ground_as_well_as_the_best_role():
    # every role passes the (lenient) gate, but only finance reaches the restricted chunk
    scores = {"employee": 0.45, "manager": 0.45, "hr": 0.45, "finance": 0.62, "leadership": 0.62}
    assert choose_min_role(scores, ROLES, 0.28, "employee") == "finance"
    # a small gap (a nearby open chunk) does not lock the question
    close = {"employee": 0.55, "manager": 0.55, "hr": 0.55, "finance": 0.57, "leadership": 0.57}
    assert choose_min_role(close, ROLES, 0.28, "employee") == "employee"


def test_min_role_falls_back_to_the_default_when_nobody_passes():
    scores = dict.fromkeys(ROLES, 0.1)
    assert choose_min_role(scores, ROLES, 0.5, "employee") == "employee"


def test_open_question_has_the_default_min_role():
    scores = dict.fromkeys(ROLES, 0.8)
    assert choose_min_role(scores, ROLES, 0.5, "employee") == "employee"


def test_select_final_keeps_top_n_and_guarantees_a_locked_question():
    ranked = [
        ("open a?", 0.9, "employee"),
        ("open b?", 0.8, "employee"),
        ("open c?", 0.7, "employee"),
        ("locked?", 0.6, "finance"),
        ("open d?", 0.5, "employee"),
    ]
    assert select_final(ranked, 3, "employee", has_restricted=True) == [
        {"question": "open a?", "min_role": "employee"},
        {"question": "open b?", "min_role": "employee"},
        {"question": "locked?", "min_role": "finance"},
    ]
    # nothing restricted in the collection → plain top-3
    assert [q["question"] for q in select_final(ranked, 3, "employee", has_restricted=False)] == [
        "open a?",
        "open b?",
        "open c?",
    ]
    # a locked question already in the top-3 → nothing swapped
    ranked2 = [ranked[0], ranked[3], ranked[1], ranked[2]]
    assert [q["question"] for q in select_final(ranked2, 3, "employee", has_restricted=True)] == [
        "open a?",
        "locked?",
        "open b?",
    ]


def test_select_final_guarantees_an_open_question_too():
    ranked = [
        ("locked a?", 0.9, "finance"),
        ("locked b?", 0.8, "hr"),
        ("locked c?", 0.7, "managers"),
        ("open?", 0.6, "employee"),
    ]
    assert [q["question"] for q in select_final(ranked, 3, "employee", has_restricted=True)] == [
        "locked a?",
        "locked b?",
        "open?",
    ]
    # nothing open among the candidates at all → nothing to swap in
    only_locked = ranked[:3]
    assert len(select_final(only_locked, 3, "employee", has_restricted=True)) == 3
