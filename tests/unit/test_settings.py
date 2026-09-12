import pytest
from pydantic import ValidationError

from app.config import Settings


def settings(**kwargs):
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://localhost/docqa",
        redis_url="redis://localhost/0",
        **kwargs,
    )


@pytest.mark.parametrize(
    "values",
    [
        {"embedding_provider": "openai", "openai_api_key": ""},
        {"rerank_provider": "cohere", "cohere_api_key": ""},
        {
            "llm_provider": "openai_compat",
            "llm_api_key": "",
            "llm_base_url": "https://provider.example/v1",
        },
        {
            "llm_provider": "openai_compat",
            "llm_api_key": "",
            "llm_base_url": "https://localhost.attacker.example/v1",
        },
        {"max_upload_mb": 0},
        {"rate_limit_query_per_minute": 0},
        {"idempotency_ttl_s": -1},
        {"demo_max_files_per_collection": 0},
        {"llm_max_tokens": -1},
        {"chunk_overlap_tokens": 500},
        {"chunk_target_tokens": 900},
    ],
)
def test_invalid_configuration_fails_before_serving(values):
    with pytest.raises(ValidationError):
        settings(**values)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:1234/v1",
        "http://host.docker.internal:11434/v1",
        "http://[::1]:11434/v1",
    ],
)
def test_local_llm_can_remain_keyless(url):
    assert (
        settings(llm_provider="openai_compat", llm_base_url=url, llm_api_key="").llm_provider
        == "openai_compat"
    )


def test_invalid_settings_do_not_print_other_configured_secrets():
    with pytest.raises(ValidationError) as error:
        settings(openai_api_key="test-secret-not-for-logs", chunk_target_tokens=900)
    assert "test-secret-not-for-logs" not in str(error.value)


@pytest.mark.parametrize("values", [{"embedding_dim": 512}, {"refusal_threshold": float("nan")}])
def test_database_dimension_and_finite_threshold_are_validated(values):
    with pytest.raises(ValidationError):
        settings(**values)


def test_fixed_dimension_accepts_environment_string(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIM", "1024")
    assert settings().embedding_dim == 1024


def test_vector_only_eval_can_disable_fts():
    assert settings(top_k_fts=0).top_k_fts == 0
    with pytest.raises(ValidationError):
        settings(top_k_fts=-1)
