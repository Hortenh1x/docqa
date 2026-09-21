import hashlib
from types import SimpleNamespace

import pytest

from eval import run_indirect_comparison as comparison_eval


class RecordingEmbeddings:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(index + 1), 1.0] for index, _ in enumerate(texts)]


def _manifest(question: str = "original question") -> dict:
    return {
        "documents": [
            {
                "filename": "fixture.pdf",
                "pdf_pages": 1,
                "role": "distractor",
            }
        ],
        "retrieval_queries": {"original": question},
        "missing_evidence_control": "missing control",
    }


@pytest.fixture
def parsed_fixture(monkeypatch):
    state = {"content": "current chunk"}
    parse_calls: list[str] = []

    class FakeParser:
        def parse(self, path):
            parse_calls.append(path.name)
            return SimpleNamespace(pages=[SimpleNamespace()])

    def fake_chunk_document(parsed):
        del parsed
        return [
            SimpleNamespace(
                chunk_index=0,
                content=state["content"],
                page_start=1,
                page_end=1,
                section_path="Section",
            )
        ]

    monkeypatch.setattr(comparison_eval, "PdfParser", FakeParser)
    monkeypatch.setattr(comparison_eval, "chunk_document", fake_chunk_document)
    return state, parse_calls


async def test_cache_rebuilds_when_current_parser_or_chunk_settings_change_rows(
    tmp_path, monkeypatch, parsed_fixture
):
    state, parse_calls = parsed_fixture
    embeddings = RecordingEmbeddings()
    monkeypatch.setattr(comparison_eval, "get_embedding_provider", lambda settings: embeddings)
    settings = SimpleNamespace(embedding_model_id="text-embedding-3-small@1024")
    paths = {"fixture.pdf": tmp_path / "fixture.pdf"}
    cache_path = tmp_path / "vectors.json.gz"

    first = await comparison_eval._load_or_build_cache(
        _manifest(), paths, settings, cache_path, refresh=False
    )
    state["content"] = "changed by current parser or chunk settings"
    second = await comparison_eval._load_or_build_cache(
        _manifest(), paths, settings, cache_path, refresh=False
    )

    assert len(parse_calls) == 2
    assert len(embeddings.calls) == 2
    assert first["rows"][0]["content"] == "current chunk"
    assert second["rows"][0]["content"] == state["content"]


async def test_verified_source_change_is_rejected_before_cache_use(tmp_path):
    document = tmp_path / "documents" / "fixture.pdf"
    document.parent.mkdir()
    document.write_bytes(b"changed source bytes")
    expected_hash = hashlib.sha256(b"expected source bytes").hexdigest()
    manifest = {
        "documents": [
            {
                "filename": "fixture.pdf",
                "url": "https://example.invalid/fixture.pdf",
                "sha256": expected_hash,
            }
        ]
    }

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        await comparison_eval._ensure_documents(manifest, tmp_path, allow_download=False)


async def test_cache_rebuilds_when_query_inputs_change(tmp_path, monkeypatch, parsed_fixture):
    _, parse_calls = parsed_fixture
    embeddings = RecordingEmbeddings()
    monkeypatch.setattr(comparison_eval, "get_embedding_provider", lambda settings: embeddings)
    settings = SimpleNamespace(embedding_model_id="text-embedding-3-small@1024")
    paths = {"fixture.pdf": tmp_path / "fixture.pdf"}
    cache_path = tmp_path / "vectors.json.gz"

    await comparison_eval._load_or_build_cache(
        _manifest(), paths, settings, cache_path, refresh=False
    )
    result = await comparison_eval._load_or_build_cache(
        _manifest("changed question"), paths, settings, cache_path, refresh=False
    )

    assert len(parse_calls) == 2
    assert len(embeddings.calls) == 2
    assert "changed question" in result["query_vectors"]
    assert "original question" not in result["query_vectors"]


async def test_cache_reuses_vectors_for_identical_current_inputs(
    tmp_path, monkeypatch, parsed_fixture
):
    _, parse_calls = parsed_fixture
    embeddings = RecordingEmbeddings()
    monkeypatch.setattr(comparison_eval, "get_embedding_provider", lambda settings: embeddings)
    settings = SimpleNamespace(embedding_model_id="text-embedding-3-small@1024")
    paths = {"fixture.pdf": tmp_path / "fixture.pdf"}
    cache_path = tmp_path / "vectors.json.gz"

    first = await comparison_eval._load_or_build_cache(
        _manifest(), paths, settings, cache_path, refresh=False
    )
    second = await comparison_eval._load_or_build_cache(
        _manifest(), paths, settings, cache_path, refresh=False
    )

    assert len(parse_calls) == 2
    assert len(embeddings.calls) == 1
    assert second == first
